import logging
from datetime import datetime

from sqlalchemy import func, or_, select
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


async def create_lead(db: AsyncSession, data: LeadCreate, client_id: int) -> Lead:
    lead = Lead(**data.model_dump(), client_id=client_id)
    db.add(lead)
    await db.commit()
    await db.refresh(lead)
    await _safe_enqueue(lead.id, client_id)
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


async def upsert_lead(db: AsyncSession, data: LeadCreate, client_id: int) -> tuple[Lead, str]:
    """Create or update a single lead. Checks by apollo_id first, then email.

    Returns (lead, action) where action is 'created' or 'updated'.
    """
    existing: Lead | None = None

    if data.apollo_id:
        result = await db.execute(
            select(Lead).where(Lead.apollo_id == data.apollo_id, Lead.client_id == client_id)
        )
        existing = result.scalar_one_or_none()

    if existing is None:
        result = await db.execute(
            select(Lead).where(Lead.email == data.email, Lead.client_id == client_id)
        )
        existing = result.scalar_one_or_none()

    if existing is None:
        lead = Lead(**data.model_dump(), client_id=client_id)
        db.add(lead)
        await db.commit()
        await db.refresh(lead)
        await _safe_enqueue(lead.id, client_id)
        return lead, "created"

    for key, value in data.model_dump(exclude_unset=True).items():
        if key == "enrichment_data" and value is not None:
            merged = dict(existing.enrichment_data or {})
            merged.update(value)
            existing.enrichment_data = merged
        elif value is not None:
            setattr(existing, key, value)
    await db.commit()
    await db.refresh(existing)
    return existing, "updated"


async def bulk_upsert_leads(
    db: AsyncSession,
    leads_data: list[LeadCreate],
    client_id: int,
    on_duplicate: str = "skip",
) -> dict[str, int]:
    """Insert leads with duplicate handling. Checks apollo_id first, then email.

    Returns {"created": N, "updated": N, "skipped": N}.
    """
    created = 0
    updated = 0
    skipped = 0
    new_leads: list[Lead] = []

    apollo_ids = [ld.apollo_id for ld in leads_data if ld.apollo_id]
    emails = [ld.email.lower() for ld in leads_data]
    by_apollo_id = await get_leads_by_apollo_ids(db, apollo_ids, client_id)
    by_email = await get_leads_by_emails(db, emails, client_id)

    for data in leads_data:
        existing_lead = (
            by_apollo_id.get(data.apollo_id) if data.apollo_id else None
        ) or by_email.get(data.email.lower())

        if existing_lead is None:
            lead = Lead(**data.model_dump(), client_id=client_id)
            db.add(lead)
            new_leads.append(lead)
            created += 1
        elif on_duplicate == "update":
            for key, value in data.model_dump(exclude_unset=True).items():
                if key == "enrichment_data" and value is not None:
                    merged = dict(existing_lead.enrichment_data or {})
                    merged.update(value)
                    existing_lead.enrichment_data = merged
                elif value is not None:
                    setattr(existing_lead, key, value)
            updated += 1
        else:
            skipped += 1

    await db.commit()

    for lead in new_leads:
        await _safe_enqueue(lead.id, client_id)

    return {"created": created, "updated": updated, "skipped": skipped}
