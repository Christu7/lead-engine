"""Concurrency tests for lead upsert correctness.

The race being covered
----------------------
Two workers receive the same lead (same apollo_id) at the same time.

  Session A: SELECT apollo_id=X  →  None   (B hasn't committed yet)
  Session B: SELECT apollo_id=X  →  None   (A hasn't committed yet)
  Session A: INSERT (apollo_id=X, email=a@example.com)  →  OK  →  COMMIT
  Session B: INSERT (apollo_id=X, email=b@example.com)  →  IntegrityError
             on ix_leads_apollo_id_client_unique
             →  ROLLBACK  →  re-query by apollo_id  →  found  →  UPDATE
             →  return "updated"

Without the IntegrityError handler the second INSERT propagates an unhandled
exception and the lead is not persisted.

Each test helper creates an independent AsyncSession so the sessions are truly
concurrent from PostgreSQL's perspective — they share no connection state and
PostgreSQL's MVCC means the SELECT in session B cannot see session A's
uncommitted row.
"""
import asyncio

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.lead import Lead
from app.schemas.lead import LeadCreate
from app.services.lead import bulk_upsert_leads, upsert_lead


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _test_db_url() -> str:
    if settings.TEST_DATABASE_URL:
        return settings.TEST_DATABASE_URL
    base, _, _ = settings.DATABASE_URL.rpartition("/")
    return f"{base}/leadengine_test"


async def _upsert_own_session(data: LeadCreate, client_id: int) -> tuple[Lead, str]:
    """Run upsert_lead inside a fresh, independent DB connection."""
    engine = create_async_engine(_test_db_url())
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as db:
            return await upsert_lead(db, data, client_id)
    finally:
        await engine.dispose()


async def _bulk_own_session(
    leads_data: list[LeadCreate], client_id: int, on_duplicate: str = "update"
) -> dict[str, int]:
    engine = create_async_engine(_test_db_url())
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as db:
            return await bulk_upsert_leads(db, leads_data, client_id, on_duplicate=on_duplicate)
    finally:
        await engine.dispose()


def _assert_no_exceptions(results: list, label: str) -> None:
    errors = [r for r in results if isinstance(r, Exception)]
    assert not errors, f"{label}: unexpected exceptions raised:\n" + "\n".join(
        f"  {type(e).__name__}: {e}" for e in errors
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestConcurrentUpsertLead:

    async def test_same_apollo_id_same_email_no_duplicate(self, db_session, seeded_client):
        """N concurrent upserts with identical (apollo_id, email) → exactly 1 row.

        The email ON CONFLICT handles this atomically even without the apollo_id fix,
        but the test establishes a baseline.
        """
        data = LeadCreate(name="Lead", email="same@upsert.com", apollo_id="ap_conc_1")

        results = await asyncio.gather(
            *[_upsert_own_session(data, seeded_client.id) for _ in range(5)],
            return_exceptions=True,
        )
        _assert_no_exceptions(results, "same apollo_id + same email")

        count = (
            await db_session.execute(
                select(func.count()).select_from(Lead).where(
                    Lead.apollo_id == "ap_conc_1",
                    Lead.client_id == seeded_client.id,
                )
            )
        ).scalar_one()
        assert count == 1, f"Expected 1 row, got {count}"

    async def test_same_apollo_id_different_emails_no_crash_no_duplicate(
        self, db_session, seeded_client
    ):
        """The critical race: same apollo_id, different emails across concurrent sessions.

        Without the IntegrityError handler the loser raises an unhandled exception
        (ix_leads_apollo_id_client_unique) and the session is left in an error state.
        With the fix the loser rollbacks, re-queries, and returns ("lead", "updated").
        """
        n = 5
        results = await asyncio.gather(
            *[
                _upsert_own_session(
                    LeadCreate(
                        name=f"Worker {i}",
                        email=f"worker_{i}@upsert.com",
                        apollo_id="ap_conc_2",
                    ),
                    seeded_client.id,
                )
                for i in range(n)
            ],
            return_exceptions=True,
        )

        _assert_no_exceptions(
            results,
            "same apollo_id + different emails — IntegrityError handler not in place",
        )

        count = (
            await db_session.execute(
                select(func.count()).select_from(Lead).where(
                    Lead.apollo_id == "ap_conc_2",
                    Lead.client_id == seeded_client.id,
                )
            )
        ).scalar_one()
        assert count == 1, (
            f"Expected 1 row, got {count} — duplicate created under concurrent inserts"
        )

    async def test_deterministic_race_via_barrier(self, db_session, seeded_client):
        """Force the exact race window: session B's SELECT completes before session A's
        INSERT, then both proceed.  Uses asyncio Events as a barrier so the ordering
        is deterministic rather than relying on scheduling luck.

        Flow:
          A: SELECT → None  →  signal B  →  wait for B's SELECT  →  INSERT → commit
          B: wait for A's signal  →  SELECT → None  →  signal A  →  INSERT → IntegrityError
             → rollback → re-query → UPDATE → "updated"
        """
        apollo_id = "ap_barrier_1"
        email_a = "barrier_a@upsert.com"
        email_b = "barrier_b@upsert.com"

        a_selected = asyncio.Event()
        b_selected = asyncio.Event()

        async def session_a() -> tuple[Lead, str]:
            engine = create_async_engine(_test_db_url())
            factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            try:
                async with factory() as db:
                    # Step 1: SELECT — expects nothing yet
                    existing = (
                        await db.execute(
                            select(Lead).where(
                                Lead.apollo_id == apollo_id,
                                Lead.client_id == seeded_client.id,
                            )
                        )
                    ).scalar_one_or_none()
                    assert existing is None
                    a_selected.set()        # tell B our SELECT is done
                    await b_selected.wait() # wait until B's SELECT is also done
                    # Step 2: INSERT — proceeds first, B will collide
                    return await upsert_lead(
                        db,
                        LeadCreate(name="Session A", email=email_a, apollo_id=apollo_id),
                        seeded_client.id,
                    )
            finally:
                await engine.dispose()

        async def session_b() -> tuple[Lead, str]:
            engine = create_async_engine(_test_db_url())
            factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            try:
                async with factory() as db:
                    await a_selected.wait()  # wait until A's SELECT is done
                    # Step 1: SELECT — still nothing (A hasn't committed yet)
                    existing = (
                        await db.execute(
                            select(Lead).where(
                                Lead.apollo_id == apollo_id,
                                Lead.client_id == seeded_client.id,
                            )
                        )
                    ).scalar_one_or_none()
                    assert existing is None
                    b_selected.set()  # signal A to proceed with its INSERT
                    # Step 2: INSERT — A commits first, so B hits the IntegrityError
                    return await upsert_lead(
                        db,
                        LeadCreate(name="Session B", email=email_b, apollo_id=apollo_id),
                        seeded_client.id,
                    )
            finally:
                await engine.dispose()

        results = await asyncio.gather(session_a(), session_b(), return_exceptions=True)
        _assert_no_exceptions(results, "barrier race")

        actions = [action for _, action in results if not isinstance(results, Exception)]  # type: ignore[misc]
        # Exactly one "created", and the loser must have returned "updated"
        assert "created" in actions
        assert "updated" in actions

        count = (
            await db_session.execute(
                select(func.count()).select_from(Lead).where(
                    Lead.apollo_id == apollo_id,
                    Lead.client_id == seeded_client.id,
                )
            )
        ).scalar_one()
        assert count == 1, f"Expected 1 row after barrier race, got {count}"

    async def test_no_apollo_id_email_only_concurrent(self, db_session, seeded_client):
        """Email-only path: ON CONFLICT handles this without our IntegrityError fix.
        Included to verify the existing path still works under concurrent load.
        """
        data = LeadCreate(name="Email Only", email="emailonly@upsert.com")

        results = await asyncio.gather(
            *[_upsert_own_session(data, seeded_client.id) for _ in range(5)],
            return_exceptions=True,
        )
        _assert_no_exceptions(results, "email-only concurrent")

        count = (
            await db_session.execute(
                select(func.count()).select_from(Lead).where(
                    Lead.email == "emailonly@upsert.com",
                    Lead.client_id == seeded_client.id,
                )
            )
        ).scalar_one()
        assert count == 1

    async def test_sequential_same_apollo_id_returns_updated(self, db_session, seeded_client):
        """Non-concurrent baseline: second upsert with the same apollo_id must return
        "updated" and must not create a second row."""
        lead_a, action_a = await upsert_lead(
            db_session,
            LeadCreate(name="First", email="seq_a@upsert.com", apollo_id="ap_seq_1"),
            seeded_client.id,
        )
        assert action_a == "created"

        lead_b, action_b = await upsert_lead(
            db_session,
            LeadCreate(name="Second", email="seq_b@upsert.com", apollo_id="ap_seq_1"),
            seeded_client.id,
        )
        assert action_b == "updated"
        assert lead_b.id == lead_a.id, "Different apollo_id upsert created a new row"

        count = (
            await db_session.execute(
                select(func.count()).select_from(Lead).where(
                    Lead.apollo_id == "ap_seq_1",
                    Lead.client_id == seeded_client.id,
                )
            )
        ).scalar_one()
        assert count == 1


@pytest.mark.integration
class TestConcurrentBulkUpsert:

    async def test_update_mode_same_apollo_id_no_crash_no_duplicate(
        self, db_session, seeded_client
    ):
        """bulk_upsert_leads in update mode handles concurrent apollo_id collisions
        via per-INSERT savepoints — the batch must not abort and must produce 1 row."""
        data = [LeadCreate(name="Bulk", email="bulk_conc@upsert.com", apollo_id="ap_bulk_1")]
        n = 4

        results = await asyncio.gather(
            *[_bulk_own_session(data, seeded_client.id, on_duplicate="update") for _ in range(n)],
            return_exceptions=True,
        )
        _assert_no_exceptions(results, "bulk update-mode concurrent")

        count = (
            await db_session.execute(
                select(func.count()).select_from(Lead).where(
                    Lead.apollo_id == "ap_bulk_1",
                    Lead.client_id == seeded_client.id,
                )
            )
        ).scalar_one()
        assert count == 1, f"Expected 1 row, got {count}"

    async def test_skip_mode_same_apollo_id_no_crash(self, db_session, seeded_client):
        """bulk_upsert_leads in skip mode must not crash on apollo_id collisions.
        Losers count the lead as skipped rather than raising an IntegrityError."""
        data = [LeadCreate(name="Skip", email="skip_conc@upsert.com", apollo_id="ap_bulk_2")]
        n = 4

        results = await asyncio.gather(
            *[_bulk_own_session(data, seeded_client.id, on_duplicate="skip") for _ in range(n)],
            return_exceptions=True,
        )
        _assert_no_exceptions(results, "bulk skip-mode concurrent")

        count = (
            await db_session.execute(
                select(func.count()).select_from(Lead).where(
                    Lead.apollo_id == "ap_bulk_2",
                    Lead.client_id == seeded_client.id,
                )
            )
        ).scalar_one()
        assert count == 1, f"Expected 1 row, got {count}"

    async def test_savepoint_isolates_single_failure_from_batch(
        self, db_session, seeded_client
    ):
        """An IntegrityError on one lead must not abort the rest of the batch.

        Without savepoints, any IntegrityError inside the loop propagates out and
        causes db.commit() to fail, losing all previously processed leads in the batch.
        With begin_nested() each INSERT has its own savepoint — the batch continues.
        """
        # Seed an existing lead so the second item in the batch will hit the
        # apollo_id partial unique index if two sessions race
        seed = Lead(
            name="Seed",
            email="seed_batch@upsert.com",
            apollo_id="ap_batch_seed",
            client_id=seeded_client.id,
        )
        db_session.add(seed)
        await db_session.commit()
        await db_session.refresh(seed)

        # Batch: first lead has a NEW apollo_id (should be created),
        # second lead reuses the seeded apollo_id (should be updated, not crash).
        batch = [
            LeadCreate(name="New Lead", email="new_batch@upsert.com", apollo_id="ap_batch_new"),
            LeadCreate(
                name="Updated Seed",
                email="updated_seed@upsert.com",
                apollo_id="ap_batch_seed",  # same as already-seeded lead
            ),
        ]
        result = await bulk_upsert_leads(
            db_session, batch, seeded_client.id, on_duplicate="update"
        )

        # Both leads must have been processed — neither aborted the batch
        assert result["created"] + result["updated"] == 2, (
            f"Expected 2 processed, got created={result['created']} "
            f"updated={result['updated']} skipped={result['skipped']}"
        )

        # New lead was created
        new_count = (
            await db_session.execute(
                select(func.count()).select_from(Lead).where(
                    Lead.apollo_id == "ap_batch_new",
                    Lead.client_id == seeded_client.id,
                )
            )
        ).scalar_one()
        assert new_count == 1
