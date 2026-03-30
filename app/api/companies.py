"""Company API endpoints.

All routes enforce client_id from the JWT (never from request body/headers).
Multi-tenancy is a hard security boundary — every query filters by client_id.
"""
import csv
import io
import json
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Query, UploadFile
from starlette.requests import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_client_id, get_current_active_user, require_admin
from app.core.input_validation import (
    ALLOWED_CSV_CONTENT_TYPES,
    MAX_CSV_FILE_SIZE,
    MAX_CSV_ROWS,
    sanitize_csv_row,
)
from app.core.rate_limit import limiter
from app.models.company import Company
from app.models.lead import Lead
from app.schemas.custom_field import CustomFieldValuesUpdate
from app.schemas.company import (
    CompanyBulkUploadResponse,
    CompanyCreate,
    CompanyDetailResponse,
    CompanyResponse,
    CompanyUpdate,
    ContactPullRequest,
)
from app.schemas.lead import LeadResponse
from app.services.company import (
    create_company,
    delete_company,
    get_company,
    get_company_by_domain,
    list_companies,
    upsert_company,
)
from app.services.csv_mapping import apply_user_mapping, parse_company_csv_row

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["companies"],
    dependencies=[Depends(get_current_active_user)],
)


# ---------------------------------------------------------------------------
# Background task helpers — each opens its own DB session, never reuses the
# request session which is closed before background tasks run.
# ---------------------------------------------------------------------------


async def _bg_enrich_company(company_id: uuid.UUID, client_id: int) -> None:
    """Background task: run Apollo org enrichment for a single company."""
    from app.core.database import async_session
    from app.services.apollo_company import ApolloCompanyEnrichmentService
    from app.services.company import get_company as _get_company

    logger.info(
        "Background: enrich_company started",
        extra={"company_id": str(company_id), "client_id": client_id},
    )
    try:
        async with async_session() as db:
            company = await _get_company(db, company_id, client_id)
            if company is None:
                logger.error(
                    "Background: enrich_company — company not found or wrong client",
                    extra={"company_id": str(company_id), "client_id": client_id},
                )
                return
            svc = ApolloCompanyEnrichmentService()
            await svc.enrich_company(db, company, client_id)
    except Exception as exc:
        logger.error(
            "Background: enrich_company failed",
            extra={"company_id": str(company_id), "client_id": client_id, "error": str(exc)},
        )


async def _bg_pull_contacts(
    company_id: uuid.UUID,
    client_id: int,
    titles: list[str],
    seniorities: list[str],
    limit: int,
) -> None:
    """Background task: pull Apollo contacts for a company and upsert as leads."""
    from app.core.database import async_session
    from app.services.apollo_company import ApolloCompanyEnrichmentService
    from app.services.company import get_company as _get_company

    logger.info(
        "Background: pull_contacts started",
        extra={"company_id": str(company_id), "client_id": client_id},
    )
    try:
        async with async_session() as db:
            company = await _get_company(db, company_id, client_id)
            if company is None:
                logger.error(
                    "Background: pull_contacts — company not found or wrong client",
                    extra={"company_id": str(company_id), "client_id": client_id},
                )
                return
            svc = ApolloCompanyEnrichmentService()
            await svc.pull_contacts_from_company(
                db, company, client_id, titles=titles, seniorities=seniorities, limit=limit
            )
    except Exception as exc:
        logger.error(
            "Background: pull_contacts failed",
            extra={"company_id": str(company_id), "client_id": client_id, "error": str(exc)},
        )


async def _bg_enrich_one(company_id: uuid.UUID, client_id: int) -> None:
    """Thin wrapper used by bulk-enrich so each company runs in its own session."""
    await _bg_enrich_company(company_id, client_id)


# ---------------------------------------------------------------------------
# Helper: inject lead_count into CompanyResponse without N+1
# ---------------------------------------------------------------------------


async def _attach_lead_counts(
    db: AsyncSession,
    companies: list[Company],
    client_id: int,
) -> list[CompanyResponse]:
    """Return CompanyResponse objects with lead_count populated via a single query."""
    if not companies:
        return []

    company_ids = [c.id for c in companies]

    count_rows = await db.execute(
        select(Lead.company_id, func.count(Lead.id).label("cnt"))
        .where(
            Lead.company_id.in_(company_ids),
            Lead.client_id == client_id,
        )
        .group_by(Lead.company_id)
    )
    lead_counts: dict[uuid.UUID, int] = {row.company_id: row.cnt for row in count_rows}

    responses = []
    for company in companies:
        resp = CompanyResponse.model_validate(company)
        resp = resp.model_copy(update={"lead_count": lead_counts.get(company.id, 0)})
        responses.append(resp)
    return responses


# ---------------------------------------------------------------------------
# Routes — static paths before parametric to avoid ambiguity
# ---------------------------------------------------------------------------


_VALID_SORT_FIELDS = {
    "name", "domain", "industry", "employee_count",
    "enrichment_status", "abm_status", "lead_count",
    "created_at", "enriched_at",
}


@router.get("/", summary="List companies")
async def list_companies_endpoint(
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    enrichment_status: str | None = None,
    abm_status: str | None = None,
    industry: str | None = None,
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
) -> dict:
    if sort_by not in _VALID_SORT_FIELDS:
        raise HTTPException(status_code=400, detail=f"Invalid sort_by '{sort_by}'")
    if sort_order not in ("asc", "desc"):
        raise HTTPException(status_code=400, detail="sort_order must be 'asc' or 'desc'")

    filters = {
        "enrichment_status": enrichment_status,
        "abm_status": abm_status,
        "industry": industry,
    }
    companies, total = await list_companies(
        db,
        client_id=client_id,
        skip=skip,
        limit=limit,
        filters=filters,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    items = await _attach_lead_counts(db, companies, client_id)
    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.post("/bulk", response_model=CompanyBulkUploadResponse, summary="Bulk upload companies from CSV")
@limiter.limit("5/minute")
async def bulk_upload_companies(
    request: Request,
    file: UploadFile,
    column_mapping: str | None = Form(None),
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
) -> CompanyBulkUploadResponse:
    """Upload companies from CSV.

    Accepts an optional ``column_mapping`` form field: a JSON object mapping
    CSV header names to LeadEngine field names.  When provided, that mapping
    is used instead of auto-detection so every column lands exactly where the
    user intended.
    """
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a .csv")

    # Content-Type check (browsers vary; reject obvious non-CSV types)
    if file.content_type and file.content_type not in ALLOWED_CSV_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unexpected content type '{file.content_type}'. Upload a CSV file.",
        )

    # File-size check: read at most MAX+1 bytes to detect overflow without buffering the world
    raw = await file.read(MAX_CSV_FILE_SIZE + 1)
    if len(raw) > MAX_CSV_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"CSV file too large. Maximum size is {MAX_CSV_FILE_SIZE // 1024 // 1024} MB.",
        )

    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded")

    # Parse the optional user-supplied column mapping
    user_mapping: dict[str, str] | None = None
    if column_mapping:
        try:
            user_mapping = json.loads(column_mapping)
            if not isinstance(user_mapping, dict):
                raise ValueError("column_mapping must be a JSON object")
        except (json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid column_mapping: {exc}")

    reader = csv.DictReader(io.StringIO(content))

    # Load all rows upfront so we can check the total before committing any writes
    rows = list(reader)
    if len(rows) > MAX_CSV_ROWS:
        raise HTTPException(
            status_code=400,
            detail=f"CSV too large. Maximum {MAX_CSV_ROWS:,} data rows allowed (got {len(rows):,}).",
        )

    created = 0
    updated = 0
    skipped = 0
    errors: list[str] = []

    for row_num, row in enumerate(rows, start=1):
        try:
            # Sanitise field values before mapping (strips control chars + formula injection)
            row = sanitize_csv_row(row)

            if user_mapping is not None:
                data = apply_user_mapping(row, user_mapping)
            else:
                data = parse_company_csv_row(row)

            if not data.get("name"):
                errors.append(f"Row {row_num}: missing required field 'name'")
                skipped += 1
                continue
            _, was_created = await upsert_company(db, data, client_id)
            if was_created:
                created += 1
            else:
                updated += 1
        except Exception as exc:
            errors.append(f"Row {row_num}: {exc}")
            skipped += 1

    return CompanyBulkUploadResponse(
        created=created,
        updated=updated,
        skipped=skipped,
        errors=errors,
    )


@router.post(
    "/bulk-enrich",
    status_code=202,
    summary="Queue all pending/failed companies for enrichment (admin only)",
)
async def bulk_enrich_companies(
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
) -> dict:
    from app.services import task_queue

    result = await db.execute(
        select(Company).where(
            Company.client_id == client_id,
            Company.enrichment_status.in_(["pending", "failed"]),
        )
    )
    companies = result.scalars().all()

    # Stagger task scores so they don't all become ready simultaneously.
    # The worker's inter-task delay further prevents API flooding.
    delay_step = settings.APOLLO_REQUEST_DELAY_MS / 1000.0
    for i, company in enumerate(companies):
        await task_queue.enqueue(
            "company_enrichment",
            {"company_id": str(company.id), "client_id": client_id, "retry_count": 0},
            delay_seconds=i * delay_step,
        )

    logger.info(
        "Bulk enrich queued",
        extra={"client_id": client_id, "queued": len(companies)},
    )
    return {
        "message": f"Queued {len(companies)} companies for enrichment",
        "queued": len(companies),
    }


@router.post("/", response_model=CompanyResponse, status_code=201, summary="Create a company")
async def create_company_endpoint(
    data: CompanyCreate,
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
) -> CompanyResponse:
    # Domain uniqueness check
    if data.domain:
        existing = await get_company_by_domain(db, data.domain, client_id)
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail=f"A company with domain '{data.domain}' already exists for this client",
            )

    company = await create_company(db, data.model_dump(exclude_none=True), client_id)
    resp = CompanyResponse.model_validate(company)
    return resp


@router.get("/{company_id}", response_model=CompanyDetailResponse, summary="Get company with linked leads")
async def get_company_endpoint(
    company_id: uuid.UUID,
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
) -> CompanyDetailResponse:
    company = await get_company(db, company_id, client_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")

    # Fetch up to 10 linked leads (client_id scoped)
    lead_result = await db.execute(
        select(Lead)
        .where(Lead.company_id == company_id, Lead.client_id == client_id)
        .order_by(Lead.created_at.desc())
        .limit(10)
    )
    leads = lead_result.scalars().all()
    lead_responses = [LeadResponse.model_validate(lead) for lead in leads]

    # Count total leads for this company
    count_result = await db.execute(
        select(func.count(Lead.id)).where(
            Lead.company_id == company_id,
            Lead.client_id == client_id,
        )
    )
    lead_count = count_result.scalar_one()

    resp = CompanyDetailResponse.model_validate(company)
    resp = resp.model_copy(update={"lead_count": lead_count, "leads": lead_responses})
    return resp


@router.patch("/{company_id}", response_model=CompanyResponse, summary="Update a company")
async def update_company_endpoint(
    company_id: uuid.UUID,
    data: CompanyUpdate,
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
) -> CompanyResponse:
    company = await get_company(db, company_id, client_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")

    update_data = data.model_dump(exclude_unset=True)
    # enrichment_data is intentionally not in CompanyUpdate — enforced by schema

    for key, value in update_data.items():
        setattr(company, key, value)

    await db.commit()
    await db.refresh(company)

    logger.info(
        "Company updated",
        extra={"company_id": str(company_id), "client_id": client_id},
    )
    resp = CompanyResponse.model_validate(company)
    return resp


@router.patch("/{company_id}/custom-fields", response_model=CompanyResponse, summary="Set custom field values on a company")
async def update_company_custom_fields(
    company_id: uuid.UUID,
    data: CustomFieldValuesUpdate,
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
) -> CompanyResponse:
    """Set custom field values on a company. Validates against active field definitions."""
    from app.services import custom_fields as cf_service

    company = await get_company(db, company_id, client_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")

    field_defs = await cf_service.get_field_definitions(db, client_id, "company")
    try:
        company = await cf_service.set_custom_field_values(db, company, data.values, field_defs, client_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    resp = CompanyResponse.model_validate(company)
    return resp


@router.delete("/{company_id}", status_code=204, summary="Soft-delete a company")
async def delete_company_endpoint(
    company_id: uuid.UUID,
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    deleted = await delete_company(db, company_id, client_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Company not found")


@router.post("/{company_id}/enrich", status_code=202, summary="Trigger Apollo org enrichment")
async def enrich_company_endpoint(
    company_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    company = await get_company(db, company_id, client_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    if company.enrichment_status == "enriching":
        raise HTTPException(status_code=409, detail="Enrichment already in progress")

    # Mark enriching immediately so concurrent calls get 409
    company.enrichment_status = "enriching"
    await db.commit()

    background_tasks.add_task(_bg_enrich_company, company_id, client_id)

    logger.info(
        "Company enrichment queued",
        extra={"company_id": str(company_id), "client_id": client_id},
    )
    return {
        "message": "Enrichment started",
        "company_id": str(company_id),
        "status": "enriching",
    }


@router.post("/{company_id}/pull-contacts", status_code=202, summary="Pull Apollo contacts as leads")
async def pull_contacts_endpoint(
    company_id: uuid.UUID,
    body: ContactPullRequest,
    background_tasks: BackgroundTasks,
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    company = await get_company(db, company_id, client_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    if not company.apollo_id:
        raise HTTPException(
            status_code=400,
            detail="Company must be enriched before pulling contacts",
        )

    background_tasks.add_task(
        _bg_pull_contacts,
        company_id,
        client_id,
        body.titles,
        body.seniorities,
        body.limit,
    )

    logger.info(
        "Contact pull queued",
        extra={"company_id": str(company_id), "client_id": client_id},
    )
    return {
        "message": "Contact pull started",
        "company_id": str(company_id),
        "status": "processing",
    }
