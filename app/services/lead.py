from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import Lead
from app.schemas.lead import LeadCreate, LeadUpdate

SORTABLE_COLUMNS = {"id", "name", "email", "company", "source", "status", "score", "created_at", "updated_at"}


async def create_lead(db: AsyncSession, data: LeadCreate) -> Lead:
    lead = Lead(**data.model_dump())
    db.add(lead)
    await db.commit()
    await db.refresh(lead)
    return lead


async def get_lead(db: AsyncSession, lead_id: int) -> Lead | None:
    return await db.get(Lead, lead_id)


async def list_leads(
    db: AsyncSession,
    *,
    limit: int = 20,
    offset: int = 0,
    source: str | None = None,
    status: str | None = None,
    score_min: int | None = None,
    score_max: int | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> tuple[list[Lead], int]:
    query = select(Lead)

    if source is not None:
        query = query.where(Lead.source == source)
    if status is not None:
        query = query.where(Lead.status == status)
    if score_min is not None:
        query = query.where(Lead.score >= score_min)
    if score_max is not None:
        query = query.where(Lead.score <= score_max)

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


async def update_lead(db: AsyncSession, lead_id: int, data: LeadUpdate) -> Lead | None:
    lead = await db.get(Lead, lead_id)
    if lead is None:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(lead, key, value)
    await db.commit()
    await db.refresh(lead)
    return lead


async def delete_lead(db: AsyncSession, lead_id: int) -> bool:
    lead = await db.get(Lead, lead_id)
    if lead is None:
        return False
    await db.delete(lead)
    await db.commit()
    return True


async def bulk_create_leads(db: AsyncSession, leads_data: list[LeadCreate]) -> list[Lead]:
    leads = [Lead(**data.model_dump()) for data in leads_data]
    db.add_all(leads)
    await db.commit()
    for lead in leads:
        await db.refresh(lead)
    return leads


async def get_leads_by_emails(db: AsyncSession, emails: list[str]) -> dict[str, Lead]:
    """Fetch existing leads by email, returning a dict keyed by lowercase email."""
    if not emails:
        return {}
    result = await db.execute(
        select(Lead).where(Lead.email.in_([e.lower() for e in emails]))
    )
    return {lead.email.lower(): lead for lead in result.scalars().all()}


async def bulk_upsert_leads(
    db: AsyncSession,
    leads_data: list[LeadCreate],
    on_duplicate: str = "skip",
) -> dict[str, int]:
    """Insert leads with duplicate email handling.

    Returns {"created": N, "updated": N, "skipped": N}.
    """
    created = 0
    updated = 0
    skipped = 0

    emails = [ld.email.lower() for ld in leads_data]
    existing = await get_leads_by_emails(db, emails)

    for data in leads_data:
        existing_lead = existing.get(data.email.lower())

        if existing_lead is None:
            db.add(Lead(**data.model_dump()))
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
    return {"created": created, "updated": updated, "skipped": skipped}
