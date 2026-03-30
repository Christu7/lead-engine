import logging
from datetime import datetime

from sqlalchemy import func, or_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.lead import Lead
from app.schemas.lead import LeadCreate, LeadUpdate
from app.services.enrichment.queue import enqueue_enrichment

logger = logging.getLogger(__name__)


def _safe_enqueue(lead_id: int, client_id: int):
    """Return a coroutine that enqueues enrichment, swallowing Redis failures.

    The lead is already persisted when this is called. A Redis outage must not
    crash the request — the lead can be enriched manually via /enrich.
    """
    import asyncio

    async def _enqueue():
        try:
            await enqueue_enrichment(lead_id, client_id)
        except Exception as exc:
            logger.error(
                "Failed to enqueue enrichment for lead %d — lead created but enrichment not queued: %s",
                lead_id,
                exc,
                extra={"lead_id": lead_id, "client_id": client_id},
            )

    return _enqueue()

SORTABLE_COLUMNS = {"id", "name", "email", "company", "source", "status", "score", "created_at", "updated_at"}


async def _try_auto_link_company(db: AsyncSession, lead: Lead, client_id: int) -> None:
    """After lead persist: try to find a matching Company by email domain and link it.

    Failures are non-fatal — lead creation must never fail because of this.
    """
    try:
        if lead.company_id is not None or not lead.email or "@" not in lead.email:
            return
        domain = lead.email.split("@", 1)[1].strip().lower()
        if not domain:
            return
        # Import here to avoid a circular import at module load time
        from app.services.company import get_company_by_domain
        company = await get_company_by_domain(db, domain, client_id)
        if company is not None:
            lead.company_id = company.id
            await db.commit()
    except Exception as exc:
        logger.warning(
            "Auto-link company lookup failed (non-fatal)",
            extra={"lead_id": lead.id, "client_id": client_id, "error": str(exc)},
        )


async def create_lead(db: AsyncSession, data: LeadCreate, client_id: int) -> Lead:
    lead = Lead(**data.model_dump(), client_id=client_id)
    db.add(lead)
    await db.commit()
    await db.refresh(lead)
    await _safe_enqueue(lead.id, client_id)
    await _try_auto_link_company(db, lead, client_id)
    return lead


async def get_lead(db: AsyncSession, lead_id: int, client_id: int) -> Lead | None:
    result = await db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.client_id == client_id)
    )
    return result.scalar_one_or_none()


async def list_leads(
    db: AsyncSession,
    *,
    client_id: int,
    limit: int = 20,
    offset: int = 0,
    source: str | None = None,
    status: str | None = None,
    score_min: int | None = None,
    score_max: int | None = None,
    search: str | None = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> tuple[list[Lead], int]:
    query = select(Lead).where(Lead.client_id == client_id)

    if source is not None:
        query = query.where(Lead.source == source)
    if status is not None:
        query = query.where(Lead.status == status)
    if score_min is not None:
        query = query.where(Lead.score >= score_min)
    if score_max is not None:
        query = query.where(Lead.score <= score_max)
    if search is not None:
        pattern = f"%{search}%"
        query = query.where(
            or_(
                Lead.name.ilike(pattern),
                Lead.email.ilike(pattern),
                Lead.company.ilike(pattern),
            )
        )
    if created_after is not None:
        query = query.where(Lead.created_at >= created_after)
    if created_before is not None:
        query = query.where(Lead.created_at <= created_before)

    # Count total before pagination
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    # Sorting
    if sort_by not in SORTABLE_COLUMNS:
        sort_by = "created_at"
    col = getattr(Lead, sort_by)
    order = col.asc() if sort_order == "asc" else col.desc()
    query = query.order_by(order).limit(limit).offset(offset)

    result = await db.execute(query)
    return list(result.scalars().all()), total


async def update_lead(db: AsyncSession, lead_id: int, data: LeadUpdate, client_id: int) -> Lead | None:
    lead = await get_lead(db, lead_id, client_id)
    if lead is None:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(lead, key, value)
    await db.commit()
    await db.refresh(lead)
    return lead


async def delete_lead(db: AsyncSession, lead_id: int, client_id: int) -> bool:
    lead = await get_lead(db, lead_id, client_id)
    if lead is None:
        return False
    await db.delete(lead)
    await db.commit()
    return True


async def get_lead_with_logs(db: AsyncSession, lead_id: int, client_id: int) -> Lead | None:
    result = await db.execute(
        select(Lead)
        .where(Lead.id == lead_id, Lead.client_id == client_id)
        .options(selectinload(Lead.enrichment_logs), selectinload(Lead.routing_logs))
    )
    return result.scalar_one_or_none()


async def get_leads_by_emails(db: AsyncSession, emails: list[str], client_id: int) -> dict[str, Lead]:
    """Fetch existing leads by email, returning a dict keyed by lowercase email."""
    if not emails:
        return {}
    result = await db.execute(
        select(Lead).where(
            Lead.email.in_([e.lower() for e in emails]),
            Lead.client_id == client_id,
        )
    )
    return {lead.email.lower(): lead for lead in result.scalars().all()}


async def get_leads_by_apollo_ids(db: AsyncSession, apollo_ids: list[str], client_id: int) -> dict[str, Lead]:
    """Fetch existing leads by apollo_id, returning a dict keyed by apollo_id."""
    if not apollo_ids:
        return {}
    result = await db.execute(
        select(Lead).where(
            Lead.apollo_id.in_(apollo_ids),
            Lead.client_id == client_id,
        )
    )
    return {lead.apollo_id: lead for lead in result.scalars().all()}


def _build_upsert_update_set(values: dict) -> dict:
    """Build the SET clause for ON CONFLICT DO UPDATE.

    - Skips id, client_id, created_at (must not be overwritten).
    - Skips None values (never overwrite an existing value with NULL).
    - enrichment_data uses a JSONB merge expression (shallow update, not replace).
    """
    skip = {"id", "client_id", "created_at"}
    update_set = {
        k: v for k, v in values.items()
        if k not in skip and k != "enrichment_data" and v is not None
    }
    # Merge JSONB only when incoming data is non-NULL.
    # Omitting enrichment_data from SET when it is None lets PostgreSQL preserve
    # the existing column value without any CASE expression — avoids the asyncpg
    # behaviour where Python None is sent as 'null'::jsonb (not SQL NULL) for
    # JSONB parameters, which caused excluded.enrichment_data IS NOT NULL to fire
    # and produce an unexpected result from the || operator.
    if values.get("enrichment_data") is not None:
        update_set["enrichment_data"] = text(
            "COALESCE(leads.enrichment_data, '{}'::jsonb) || excluded.enrichment_data"
        )
    return update_set


async def upsert_lead(db: AsyncSession, data: LeadCreate, client_id: int) -> tuple[Lead, str]:
    """Create or update a single lead. Checks by apollo_id first, then uses
    INSERT ... ON CONFLICT (email, client_id) DO UPDATE to atomically handle
    the email-based upsert without a SELECT-then-INSERT race condition.

    Returns (lead, action) where action is 'created' or 'updated'.
    """
    # Apollo ID: still requires a SELECT because the partial unique index
    # (apollo_id, client_id WHERE apollo_id IS NOT NULL) can't be used as the
    # ON CONFLICT target together with the email constraint in one statement.
    if data.apollo_id:
        result = await db.execute(
            select(Lead).where(Lead.apollo_id == data.apollo_id, Lead.client_id == client_id)
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            for key, value in data.model_dump(exclude_unset=True).items():
                if key == "enrichment_data" and value is not None:
                    merged = dict(existing.enrichment_data or {})
                    merged.update(value)
                    existing.enrichment_data = merged
                elif value is not None:
                    setattr(existing, key, value)
            await db.commit()
            await db.refresh(existing)
            await _try_auto_link_company(db, existing, client_id)
            return existing, "updated"

    # Pre-check: used only for action-label reporting ("created" vs "updated").
    # The unique constraint + ON CONFLICT below is what prevents duplicates —
    # the race window here only affects the metadata, not correctness.
    pre_existing_id = (
        await db.execute(
            select(Lead.id).where(Lead.email == data.email, Lead.client_id == client_id)
        )
    ).scalar_one_or_none()

    # Atomic upsert on (email, client_id).
    # Use Lead.__table__ (Core, not ORM) so SQLAlchemy does NOT attempt to map
    # the result back to a Lead ORM object — that would corrupt the identity map
    # and cause subsequent SELECTs to return stale/partial data.
    values = {**data.model_dump(), "client_id": client_id}
    stmt = (
        pg_insert(Lead.__table__)
        .values(**values)
        .on_conflict_do_update(
            constraint="uq_lead_email_client",
            set_=_build_upsert_update_set(values),
        )
    )
    await db.execute(stmt)
    await db.commit()

    result = await db.execute(
        select(Lead).where(Lead.email == data.email, Lead.client_id == client_id)
    )
    lead = result.scalar_one()
    was_updated = pre_existing_id is not None

    action = "updated" if was_updated else "created"
    if not was_updated:
        await _safe_enqueue(lead.id, client_id)
    await _try_auto_link_company(db, lead, client_id)
    return lead, action


async def bulk_upsert_leads(
    db: AsyncSession,
    leads_data: list[LeadCreate],
    client_id: int,
    on_duplicate: str = "skip",
) -> dict[str, int]:
    """Insert leads with duplicate handling. Checks apollo_id first, then email.

    Uses INSERT ... ON CONFLICT to handle races in the window between the
    pre-fetch and the actual insert.

    Returns {"created": N, "updated": N, "skipped": N}.
    """
    created = 0
    updated = 0
    skipped = 0
    new_lead_ids: list[int] = []
    updated_lead_ids: list[int] = []

    apollo_ids = [ld.apollo_id for ld in leads_data if ld.apollo_id]
    emails = [ld.email.lower() for ld in leads_data]
    by_apollo_id = await get_leads_by_apollo_ids(db, apollo_ids, client_id)
    by_email = await get_leads_by_emails(db, emails, client_id)

    for data in leads_data:
        existing_lead = (
            by_apollo_id.get(data.apollo_id) if data.apollo_id else None
        ) or by_email.get(data.email.lower())

        if existing_lead is None:
            values = {**data.model_dump(), "client_id": client_id}
            if on_duplicate == "update":
                # Atomic upsert — handles races in the pre-fetch window.
                # Lead.__table__ avoids ORM identity-map pollution (same reason as upsert_lead).
                stmt = (
                    pg_insert(Lead.__table__)
                    .values(**values)
                    .on_conflict_do_update(
                        constraint="uq_lead_email_client",
                        set_=_build_upsert_update_set(values),
                    )
                    .returning(text("id"), text("(xmax <> 0) as was_updated"))
                )
                row = (await db.execute(stmt)).first()
                if bool(row[1]):
                    updated += 1
                else:
                    new_lead_ids.append(row[0])
                    created += 1
            else:
                # skip mode: DO NOTHING on email conflict — still atomic
                stmt = (
                    pg_insert(Lead.__table__)
                    .values(**values)
                    .on_conflict_do_nothing()
                    .returning(text("id"))
                )
                row = (await db.execute(stmt)).first()
                if row:
                    new_lead_ids.append(row[0])
                    created += 1
                else:
                    skipped += 1  # concurrent insert or pre-fetch miss
        elif on_duplicate == "update":
            for key, value in data.model_dump(exclude_unset=True).items():
                if key == "enrichment_data" and value is not None:
                    merged = dict(existing_lead.enrichment_data or {})
                    merged.update(value)
                    existing_lead.enrichment_data = merged
                elif value is not None:
                    setattr(existing_lead, key, value)
            updated_lead_ids.append(existing_lead.id)
            updated += 1
        else:
            skipped += 1

    await db.commit()

    for lead_id in new_lead_ids:
        await _safe_enqueue(lead_id, client_id)

    for lead_id in updated_lead_ids:
        await _safe_enqueue(lead_id, client_id)

    return {"created": created, "updated": updated, "skipped": skipped}
