import logging
import uuid
from re import sub

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.lead import Lead

logger = logging.getLogger(__name__)


def _normalize_domain(raw: str) -> str:
    """Strip protocol, www., and trailing slash from a domain/URL."""
    raw = raw.strip()
    for prefix in ("https://", "http://"):
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
    if raw.startswith("www."):
        raw = raw[4:]
    raw = raw.rstrip("/")
    return raw.lower()


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------


async def get_company(
    db: AsyncSession, company_id: uuid.UUID, client_id: int
) -> Company | None:
    result = await db.execute(
        select(Company).where(
            Company.id == company_id,
            Company.client_id == client_id,
        )
    )
    return result.scalar_one_or_none()


async def get_company_by_domain(
    db: AsyncSession, domain: str, client_id: int
) -> Company | None:
    normalized = _normalize_domain(domain)
    result = await db.execute(
        select(Company).where(
            Company.domain == normalized,
            Company.client_id == client_id,
        )
    )
    return result.scalar_one_or_none()


async def get_company_by_apollo_id(
    db: AsyncSession, apollo_id: str, client_id: int
) -> Company | None:
    result = await db.execute(
        select(Company).where(
            Company.apollo_id == apollo_id,
            Company.client_id == client_id,
        )
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


async def list_companies(
    db: AsyncSession,
    client_id: int,
    skip: int = 0,
    limit: int = 20,
    filters: dict | None = None,
) -> tuple[list[Company], int]:
    query = select(Company).where(Company.client_id == client_id)

    if filters:
        if filters.get("enrichment_status"):
            query = query.where(Company.enrichment_status == filters["enrichment_status"])
        if filters.get("abm_status"):
            query = query.where(Company.abm_status == filters["abm_status"])
        if filters.get("industry"):
            query = query.where(Company.industry == filters["industry"])

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    query = query.order_by(Company.created_at.desc()).limit(limit).offset(skip)
    result = await db.execute(query)
    return list(result.scalars().all()), total


# ---------------------------------------------------------------------------
# Create / Upsert / Delete
# ---------------------------------------------------------------------------


async def create_company(db: AsyncSession, data: dict, client_id: int) -> Company:
    if "domain" in data and data["domain"]:
        data = dict(data)
        data["domain"] = _normalize_domain(data["domain"])

    company = Company(**data, client_id=client_id)
    db.add(company)
    await db.commit()
    await db.refresh(company)
    logger.info(
        "Company created",
        extra={"company_id": str(company.id), "client_id": client_id, "company_name": company.name},
    )
    return company


async def upsert_company(
    db: AsyncSession, data: dict, client_id: int
) -> tuple[Company, bool]:
    """Create or update a company. Match: apollo_id → domain → create new.

    On match, only updates fields that have non-None values in data.
    Returns (company, created).
    """
    data = dict(data)
    if data.get("domain"):
        data["domain"] = _normalize_domain(data["domain"])

    existing: Company | None = None

    # Match by apollo_id first
    if data.get("apollo_id"):
        existing = await get_company_by_apollo_id(db, data["apollo_id"], client_id)

    # Then by domain
    if existing is None and data.get("domain"):
        existing = await get_company_by_domain(db, data["domain"], client_id)

    if existing is None:
        company = Company(**data, client_id=client_id)
        db.add(company)
        await db.commit()
        await db.refresh(company)
        logger.info(
            "Company created via upsert",
            extra={"company_id": str(company.id), "client_id": client_id},
        )
        return company, True

    # Update only non-None fields; never overwrite with None
    for key, value in data.items():
        if key in ("id", "client_id"):
            continue
        if value is not None:
            setattr(existing, key, value)

    await db.commit()
    await db.refresh(existing)
    logger.info(
        "Company updated via upsert",
        extra={"company_id": str(existing.id), "client_id": client_id},
    )
    return existing, False


async def delete_company(
    db: AsyncSession, company_id: uuid.UUID, client_id: int
) -> bool:
    """Soft delete: set abm_status='inactive'. Returns False if not found."""
    company = await get_company(db, company_id, client_id)
    if company is None:
        return False
    company.abm_status = "inactive"
    await db.commit()
    logger.info(
        "Company soft-deleted",
        extra={"company_id": str(company_id), "client_id": client_id},
    )
    return True


async def auto_link_leads_by_domain(
    db: AsyncSession, company: Company, client_id: int
) -> None:
    """Find unlinked leads matching company.name or company.domain and link them."""
    conditions = []
    if company.name:
        conditions.append(Lead.company.ilike(company.name))
    if company.domain:
        conditions.append(
            Lead.enrichment_data["company_domain"].astext == company.domain
        )

    if not conditions:
        return

    result = await db.execute(
        select(Lead).where(
            Lead.client_id == client_id,
            Lead.company_id.is_(None),
            or_(*conditions),
        )
    )
    leads = result.scalars().all()

    for lead in leads:
        lead.company_id = company.id

    if leads:
        await db.commit()

    logger.info(
        "Auto-linked leads to company",
        extra={
            "company_id": str(company.id),
            "client_id": client_id,
            "leads_linked": len(leads),
        },
    )
