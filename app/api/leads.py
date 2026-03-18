import csv
import io
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_client_id, get_current_active_user
from app.services.ai_enrichment import run_analysis_for_lead
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

    try:
        content = (await file.read()).decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded")

    reader = csv.DictReader(io.StringIO(content))
    profile = detect_format(reader.fieldnames)

    valid_leads: list[LeadCreate] = []
    errors: list[BulkImportRow] = []
    total_rows = 0

    for row_num, row in enumerate(reader, start=1):
        total_rows += 1
        mapped = map_row(row, profile)
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
    lead.enrichment_data = None
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


@router.delete("/{lead_id}", status_code=204)
async def delete_lead(
    lead_id: int,
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
):
    deleted = await lead_service.delete_lead(db, lead_id, client_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Lead not found")
