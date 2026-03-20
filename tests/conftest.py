"""
Shared pytest fixtures.

Integration fixtures require a live PostgreSQL instance. They use
TEST_DATABASE_URL from settings (falls back to DATABASE_URL with _test suffix).

Unit tests use mocks and never touch the database.

Design note on event-loop scopes
---------------------------------
pytest-asyncio (asyncio_mode=auto) gives each test its own function-scoped
event loop by default.  SQLAlchemy's asyncpg driver is strict: a connection
pool created in one event loop cannot be used from another.

To avoid the session-vs-function event loop mismatch we:
  1. Create and drop tables inside plain asyncio.run() calls (sync fixtures,
     outside pytest's loop management).
  2. Give every test its own short-lived engine + session (function-scoped).
     The extra engine-creation overhead is negligible for an in-process DB.
"""
import asyncio
import re
from unittest.mock import AsyncMock, patch

import asyncpg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.main import app
from app.services.auth import hash_api_key


# ---------------------------------------------------------------------------
# Determine test database URL
# ---------------------------------------------------------------------------
def _build_test_db_url() -> str:
    if settings.TEST_DATABASE_URL:
        return settings.TEST_DATABASE_URL
    # Replace only the database name (last path segment), not credentials.
    # DATABASE_URL format: scheme://user:pass@host:port/dbname
    base, _, _ = settings.DATABASE_URL.rpartition("/")
    return f"{base}/leadengine_test"


_TEST_DB_URL = _build_test_db_url()


# ---------------------------------------------------------------------------
# One-time DB and table setup (session-scoped, sync, uses asyncio.run())
# ---------------------------------------------------------------------------


def _run(coro):
    """Run a coroutine synchronously in a fresh event loop."""
    return asyncio.run(coro)


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Create the test database and all tables once per test session.

    Uses asyncio.run() so there is no interaction with pytest-asyncio's
    function-scoped event loops.
    """
    db_name = _TEST_DB_URL.rpartition("/")[2]
    admin_dsn = re.sub(r"/[^/]+$", "/postgres", _TEST_DB_URL).replace(
        "postgresql+asyncpg://", ""
    )

    async def _ensure_db():
        try:
            conn = await asyncpg.connect(dsn=f"postgresql://{admin_dsn}")
            exists = await conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1", db_name
            )
            if not exists:
                await conn.execute(f'CREATE DATABASE "{db_name}"')
            await conn.close()
        except Exception as exc:
            pytest.skip(
                f"Cannot reach test database — skipping integration tests: {exc}"
            )

    async def _create_tables():
        engine = create_async_engine(_TEST_DB_URL)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    async def _drop_tables():
        engine = create_async_engine(_TEST_DB_URL)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()

    _run(_ensure_db())
    _run(_create_tables())
    yield
    _run(_drop_tables())


# ---------------------------------------------------------------------------
# Per-test DB session — fresh engine per test, TRUNCATE after each
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session():
    """Yields a per-test AsyncSession backed by its own engine.

    Tables are truncated after each test for isolation.
    A fresh engine per test avoids event-loop-scope conflicts with asyncpg.
    """
    engine = create_async_engine(_TEST_DB_URL)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
        # Clear any transaction that the test may have left in a bad state
        try:
            await session.rollback()
        except Exception:
            pass
        # Truncate all tables for next test
        try:
            table_names = ", ".join(Base.metadata.tables.keys())
            await session.execute(
                text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE")
            )
            await session.commit()
        except Exception:
            await session.rollback()
    await engine.dispose()


# ---------------------------------------------------------------------------
# HTTP client with get_db override
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def http_client(db_session):
    """AsyncClient whose get_db dependency is wired to the test session."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def _make_token(user_id: int = 1, role: str = "member", client_id: int = 1) -> str:
    return create_access_token(
        user_id=user_id,
        email=f"user{user_id}@test.com",
        role=role,
        active_client_id=client_id,
    )


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def member_token() -> str:
    return _make_token(user_id=1, role="member", client_id=1)


@pytest.fixture
def admin_token() -> str:
    return _make_token(user_id=2, role="admin", client_id=1)


@pytest_asyncio.fixture
async def seeded_users(db_session, seeded_client):
    """Insert a member (id=1) and admin (id=2) user, both linked to seeded_client.

    TRUNCATE RESTART IDENTITY guarantees the first-inserted user gets id=1 and the
    second gets id=2, which matches the hardcoded values in member_token/admin_token.
    """
    from app.core.security import hash_password
    from app.models.user import User, UserClient

    member = User(
        email="member@test.com",
        hashed_password=hash_password("test"),
        role="member",
        is_active=True,
    )
    admin = User(
        email="admin@test.com",
        hashed_password=hash_password("test"),
        role="admin",
        is_active=True,
    )
    db_session.add_all([member, admin])
    await db_session.commit()
    await db_session.refresh(member)
    await db_session.refresh(admin)
    db_session.add_all([
        UserClient(user_id=member.id, client_id=seeded_client.id),
        UserClient(user_id=admin.id, client_id=seeded_client.id),
    ])
    await db_session.commit()
    return {"member": member, "admin": admin}


@pytest_asyncio.fixture
async def authenticated_client(http_client, member_token, seeded_users):
    """HTTP client authenticated as a member user (user row seeded in DB)."""
    http_client.headers.update(_auth_headers(member_token))
    return http_client


@pytest_asyncio.fixture
async def admin_client(http_client, admin_token, seeded_users):
    """HTTP client authenticated as an admin user (user row seeded in DB)."""
    http_client.headers.update(_auth_headers(admin_token))
    return http_client


# ---------------------------------------------------------------------------
# Seeded client/lead fixtures for integration tests
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Prevent Redis calls in tests that don't test the enrichment queue
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def mock_enqueue_enrichment():
    """Patch enqueue_enrichment so webhook/lead-creation tests never touch Redis.

    Tests that explicitly test the enrichment pipeline call pipeline.run()
    directly and never go through enqueue_enrichment, so this patch is safe
    to apply globally.
    """
    with patch(
        "app.services.lead.enqueue_enrichment", new_callable=AsyncMock
    ):
        yield


@pytest_asyncio.fixture
async def seeded_client(db_session):
    """Insert a Client row and return it."""
    from app.models.client import Client

    client = Client(name="Test Client", settings={})
    db_session.add(client)
    await db_session.commit()
    await db_session.refresh(client)
    return client


@pytest_asyncio.fixture
async def seeded_api_key(db_session, seeded_client):
    """Insert an ApiKey linked to seeded_client and return the raw key string."""
    from app.models.user import ApiKey

    raw_key = "test-api-key-12345"
    api_key = ApiKey(
        key=hash_api_key(raw_key),  # store the hash, never the plaintext
        name="test",
        client_id=seeded_client.id,
        is_active=True,
    )
    db_session.add(api_key)
    await db_session.commit()
    return raw_key  # return the raw key so tests can send it in headers
