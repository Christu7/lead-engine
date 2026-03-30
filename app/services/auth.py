import hashlib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_password
from app.models.client import Client
from app.models.user import ApiKey, User, UserClient


def hash_api_key(raw_key: str) -> str:
    """Return the SHA-256 hex digest of a raw API key.

    Keys are stored as hashes so that a DB breach does not expose usable credentials.
    Always hash before storing or looking up.
    """
    return hashlib.sha256(raw_key.encode()).hexdigest()


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User | None:
    user = await get_user_by_email(db, email)
    if user is None:
        return None
    if not user.hashed_password:
        return None  # OAuth-only account; no password set
    if not verify_password(password, user.hashed_password):
        return None
    if not user.is_active:
        return None
    return user


async def find_or_create_google_user(db: AsyncSession, email: str, google_id: str) -> User:
    result = await db.execute(select(User).where(User.google_id == google_id))
    user = result.scalar_one_or_none()
    if user:
        return user

    # Existing email/password account — link the Google ID
    user = await get_user_by_email(db, email)
    if user:
        user.google_id = google_id
        await db.commit()
        await db.refresh(user)
        return user

    # New user via Google
    user = User(email=email, google_id=google_id, hashed_password=None, role="member")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def get_user_clients(db: AsyncSession, user_id: int, role: str) -> list[Client]:
    """Return all active clients this user can access.

    Inactive (soft-deleted) workspaces are excluded for all roles — they must
    not appear in the workspace switcher even for superadmins.  The admin
    management panel uses a separate query that includes inactive workspaces.

    superadmin → every active client in the system
    admin / member → only active clients explicitly assigned via user_clients
    """
    if role == "superadmin":
        result = await db.execute(
            select(Client).where(Client.is_active == True).order_by(Client.id)  # noqa: E712
        )
    else:
        result = await db.execute(
            select(Client)
            .join(UserClient, Client.id == UserClient.client_id)
            .where(UserClient.user_id == user_id, Client.is_active == True)  # noqa: E712
            .order_by(Client.id)
        )
    return list(result.scalars().all())


async def get_default_client_id(db: AsyncSession, user_id: int, role: str) -> int | None:
    clients = await get_user_clients(db, user_id, role)
    return clients[0].id if clients else None


async def invalidate_user_tokens(db: AsyncSession, user_id: int) -> None:
    """Bump token_version so all currently-issued JWTs for this user are rejected.

    Called when a user is removed from a client so their existing tokens
    (which still embed the old client_id) are immediately invalidated.
    """
    user = await get_user_by_id(db, user_id)
    if user is not None:
        user.token_version = (user.token_version or 1) + 1
        await db.commit()


async def get_api_key(db: AsyncSession, key: str) -> ApiKey | None:
    """Look up an API key by comparing SHA-256 hashes.

    The raw key is never stored — only its hash.
    """
    result = await db.execute(
        select(ApiKey).where(ApiKey.key == hash_api_key(key), ApiKey.is_active == True)  # noqa: E712
    )
    return result.scalar_one_or_none()
