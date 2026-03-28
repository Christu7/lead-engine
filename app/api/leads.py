import asyncio
import csv
import io
import logging
import uuid
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, UploadFile
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.core.database import get_db
from app.core.deps import get_client_id, get_current_active_user
from app.core.input_validation import (
    ALLOWED_CSV_CONTENT_TYPES,
    MAX_CSV_FILE_SIZE,
    MAX_CSV_ROWS,
    sanitize_csv_row,
)
from app.core.rate_limit import limiter
from app.core.security import validate_webhook_url
from app.schemas.export import ExportRequest, WebhookExportRequest, WebhookExportResponse
from app.services import export as export_service
from app.services.ai_enrichment import run_analysis_for_lead
from app.schemas.custom_field import CustomFieldValuesUpdate
from app.schemas.lead import (
    BulkImportResponse,
    BulkImportRow,
    LeadCreate,
    LeadDetailResponse,
    LeadListResponse,
    LeadResponse,
    LeadUpdate,
)
from app.services import lead as lead_service
from app.services import custom_fields as cf_service
from app.services.csv_mapping import detect_format, map_row
from app.schemas.routing import RoutingResult
from app.services.enrichment.queue import enqueue_enrichment
from app.services.routing import route_lead
from app.services.scoring import score_lead

router = APIRouter(
    prefix="/leads",
    tags=["leads"],
    dependencies=[Depends(get_current_active_user)],
)


@router.post("/", response_model=LeadResponse, status_code=201)
async def create_lead(
    data: LeadCreate,
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
):
    lead = await lead_service.create_lead(db, data, client_id)
    return lead


@router.get("/", response_model=LeadListResponse)
async def list_leads(
    client_id: int = Depends(get_client_id),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    source: str | None = None,
    status: str | None = None,
    score_min: int | None = Query(None, ge=0, le=100),
    score_max: int | None = Query(None, ge=0, le=100),
    search: str | None = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    sort_by: str = "created_at",
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
):
    items, total = await lead_service.list_leads(
        db,
        client_id=client_id,
        limit=limit,
        offset=offset,
        source=source,
        status=status,
        score_min=score_min,
        score_max=score_max,
        search=search,
        created_after=created_after,
        created_before=created_before,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return LeadListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post("/bulk", response_model=BulkImportResponse, status_code=201)
async def bulk_import(
    file: UploadFile,
    client_id: int = Depends(get_client_id),
    on_duplicate: str = Query("skip", pattern="^(skip|update)$"),
    db: AsyncSession = Depends(get_db),
):
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a .csv")

    if file.content_type and file.content_type not in ALLOWED_CSV_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unexpected content type '{file.content_type}'. Upload a CSV file.",
        )

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

    reader = csv.DictReader(io.StringIO(content))
    profile = detect_format(reader.fieldnames)

    rows = list(reader)
    if len(rows) > MAX_CSV_ROWS:
        raise HTTPException(
            status_code=400,
            detail=f"CSV too large. Maximum {MAX_CSV_ROWS:,} data rows allowed (got {len(rows):,}).",
        )

    # Fetch active custom field definitions once, before the row loop
    lead_field_defs = await cf_service.get_field_definitions(db, client_id, "lead")
    # Build lookup: normalized key/label → field_def (keys win over labels on collision)
    _custom_by_label: dict[str, Any] = {fd.field_label.strip().lower(): fd for fd in lead_field_defs}
    _custom_by_key: dict[str, Any] = {fd.field_key: fd for fd in lead_field_defs}
    custom_field_lookup: dict[str, Any] = {**_custom_by_label, **_custom_by_key}

    # Standard LeadCreate field names — don't treat these as custom fields
    _STANDARD_LEAD_FIELDS = frozenset(
        {"name", "email", "phone", "company", "title", "source", "apollo_id", "status", "enrichment_data"}
    )

    valid_leads: list[LeadCreate] = []
    errors: list[BulkImportRow] = []
    total_rows = 0

    for row_num, row in enumerate(rows, start=1):
        total_rows += 1
        row = sanitize_csv_row(row)
        mapped = map_row(row, profile)

        # Auto-map CSV columns that match a custom field key or label
        custom_values: dict[str, Any] = {}
        for csv_col, raw_val in row.items():
            col_lower = csv_col.strip().lower()
            if col_lower in _STANDARD_LEAD_FIELDS:
                continue
            fd = custom_field_lookup.get(col_lower)
            if fd is None:
                continue
            # Empty cell → null (not empty string)
            value = raw_val.strip() if isinstance(raw_val, str) else raw_val
            if value == "":
                value = None
            if value is None:
                continue
            valid, msg = cf_service.validate_custom_field_value(fd, value)
            if not valid:
                logger.warning(
                    "Bulk import row %d: custom field %r value %r invalid — %s",
                    row_num, fd.field_key, value, msg,
                )
                continue
            custom_values[fd.field_key] = value

        if custom_values:
            existing_enrichment = mapped.get("enrichment_data") or {}
            existing_custom = existing_enrichment.get("custom_fields") or {}
            merged_custom = {**existing_custom, **custom_values}
            mapped["enrichment_data"] = {**existing_enrichment, "custom_fields": merged_custom}

        try:
            lead_data = LeadCreate(**mapped)
            valid_leads.append(lead_data)
        except ValidationError as e:
            row_errors = [err["msg"] for err in e.errors()]
            errors.append(BulkImportRow(row=row_num, errors=row_errors))

    counts = {"created": 0, "updated": 0, "skipped": 0}
    if valid_leads:
        counts = await lead_service.bulk_upsert_leads(db, valid_leads, client_id, on_duplicate)

    return BulkImportResponse(
        total=total_rows,
        created=counts["created"],
        updated=counts["updated"],
        skipped=counts["skipped"],
        failed=len(errors),
        errors=errors,
    )


# ---------------------------------------------------------------------------
# Export endpoints — must be registered before /{lead_id} catch-all routes
# ---------------------------------------------------------------------------


@router.post("/export/csv", status_code=200)
async def export_leads_csv(
    request: ExportRequest,
    background_tasks: BackgroundTasks,
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
):
    """Export filtered leads as a CSV file (max 10,000 rows)."""
    csv_text, row_count = await export_service.generate_csv(db, client_id, request)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"leads_export_{timestamp}.csv"
    return Response(
        content=csv_text.encode("utf-8"),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Export-Count": str(row_count),
        },
    )


@router.post("/export/webhook", response_model=WebhookExportResponse, status_code=202)
@limiter.limit("10/minute")
async def export_leads_webhook(
    http_request: Request,
    request: WebhookExportRequest,
    background_tasks: BackgroundTasks,
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
):
    """Dispatch filtered leads to a webhook URL in batches. Returns 202 immediately."""
    # SSRF protection: verify the caller-supplied URL resolves to a public address.
    try:
        await asyncio.to_thread(validate_webhook_url, request.webhook_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    total_leads = await export_service.count_export_leads(db, client_id, request.filters)
    total_batches = max(1, -(-total_leads // request.batch_size))  # ceiling division
    export_id = str(uuid.uuid4())

    background_tasks.add_task(
        export_service.dispatch_webhook_export,
        webhook_url=request.webhook_url,
        client_id=client_id,
        filters=request.filters,
        batch_size=request.batch_size,
        include_enrichment=request.include_enrichment,
        include_ai_analysis=request.include_ai_analysis,
        export_id=export_id,
    )

    # Mask the webhook URL — expose only the domain for the response
    parsed = urlparse(request.webhook_url)
    masked_url = f"https://{parsed.netloc}"

    return WebhookExportResponse(
        export_id=export_id,
        total_leads=total_leads,
        total_batches=total_batches,
        status="dispatched",
        webhook_url=masked_url,
    )


@router.get("/{lead_id}/detail", response_model=LeadDetailResponse)
async def get_lead_detail(
    lead_id: int,
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
):
    lead = await lead_service.get_lead_with_logs(db, lead_id, client_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@router.get("/{lead_id}", response_model=LeadResponse)
async def get_lead(
    lead_id: int,
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
):
    lead = await lead_service.get_lead(db, lead_id, client_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@router.patch("/{lead_id}", response_model=LeadResponse)
async def update_lead(
    lead_id: int,
    data: LeadUpdate,
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
):
    lead = await lead_service.update_lead(db, lead_id, data, client_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@router.post("/{lead_id}/enrich", response_model=LeadResponse)
async def enrich_lead(
    lead_id: int,
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
):
    lead = await lead_service.get_lead(db, lead_id, client_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    if lead.enrichment_status == "enriching":
        raise HTTPException(status_code=409, detail="Enrichment already in progress")
    # Preserve custom fields when clearing enrichment data for re-enrichment
    existing_custom = (lead.enrichment_data or {}).get("custom_fields")
    lead.enrichment_data = {"custom_fields": existing_custom} if existing_custom else None
    lead.enrichment_status = "pending"
    await db.commit()
    await db.refresh(lead)
    await enqueue_enrichment(lead.id, client_id)
    return lead


@router.post("/{lead_id}/score", response_model=LeadResponse)
async def rescore_lead(
    lead_id: int,
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
):
    lead = await lead_service.get_lead(db, lead_id, client_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    await score_lead(db, lead, client_id)
    await db.commit()
    await db.refresh(lead)
    return lead


@router.post("/{lead_id}/route", response_model=RoutingResult)
async def route_lead_endpoint(
    lead_id: int,
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
):
    lead = await lead_service.get_lead(db, lead_id, client_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    result = await route_lead(db, lead, client_id)
    await db.commit()
    return result


@router.post("/{lead_id}/ai-analyze", status_code=202)
async def trigger_ai_analysis(
    lead_id: int,
    background_tasks: BackgroundTasks,
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
):
    """Trigger AI analysis for a lead. Returns 202 immediately; analysis runs in the background."""
    lead = await lead_service.get_lead(db, lead_id, client_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    if lead.ai_status == "analyzing":
        raise HTTPException(status_code=409, detail="Analysis already in progress")

    # Mark as analyzing before returning so concurrent calls get 409
    lead.ai_status = "analyzing"
    await db.commit()

    background_tasks.add_task(run_analysis_for_lead, lead_id, client_id)
    return {"message": "AI analysis started", "lead_id": lead_id, "status": "analyzing"}


@router.patch("/{lead_id}/custom-fields", response_model=LeadResponse)
async def update_lead_custom_fields(
    lead_id: int,
    data: CustomFieldValuesUpdate,
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
):
    """Set custom field values on a lead. Validates against active field definitions."""
    from app.services import custom_fields as cf_service

    lead = await lead_service.get_lead(db, lead_id, client_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")

    field_defs = await cf_service.get_field_definitions(db, client_id, "lead")
    try:
        lead = await cf_service.set_custom_field_values(db, lead, data.values, field_defs, client_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return lead


@router.delete("/{lead_id}", status_code=204)
async def delete_lead(
    lead_id: int,
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
):
    deleted = await lead_service.delete_lead(db, lead_id, client_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Lead not found")
