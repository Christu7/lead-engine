import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.lead import (
    BulkImportResponse,
    BulkImportRow,
    LeadCreate,
    LeadListResponse,
    LeadResponse,
    LeadUpdate,
)
from app.services import lead as lead_service

router = APIRouter(prefix="/leads", tags=["leads"])


@router.post("/", response_model=LeadResponse, status_code=201)
async def create_lead(data: LeadCreate, db: AsyncSession = Depends(get_db)):
    lead = await lead_service.create_lead(db, data)
    return lead


@router.get("/", response_model=LeadListResponse)
async def list_leads(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    source: str | None = None,
    status: str | None = None,
    score_min: int | None = Query(None, ge=0, le=100),
    score_max: int | None = Query(None, ge=0, le=100),
    sort_by: str = "created_at",
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
):
    items, total = await lead_service.list_leads(
        db,
        limit=limit,
        offset=offset,
        source=source,
        status=status,
        score_min=score_min,
        score_max=score_max,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return LeadListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post("/bulk", response_model=BulkImportResponse, status_code=201)
async def bulk_import(file: UploadFile, db: AsyncSession = Depends(get_db)):
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a .csv")

    try:
        content = (await file.read()).decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded")

    reader = csv.DictReader(io.StringIO(content))
    valid_leads: list[LeadCreate] = []
    errors: list[BulkImportRow] = []

    for row_num, row in enumerate(reader, start=1):
        # Convert empty strings to None for optional fields
        cleaned = {k: (v if v != "" else None) for k, v in row.items()}
        try:
            lead_data = LeadCreate(**cleaned)
            valid_leads.append(lead_data)
        except ValidationError as e:
            row_errors = [err["msg"] for err in e.errors()]
            errors.append(BulkImportRow(row=row_num, errors=row_errors))

    created_leads = []
    if valid_leads:
        created_leads = await lead_service.bulk_create_leads(db, valid_leads)

    return BulkImportResponse(
        created=len(created_leads),
        failed=len(errors),
        errors=errors,
    )


@router.get("/{lead_id}", response_model=LeadResponse)
async def get_lead(lead_id: int, db: AsyncSession = Depends(get_db)):
    lead = await lead_service.get_lead(db, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@router.patch("/{lead_id}", response_model=LeadResponse)
async def update_lead(lead_id: int, data: LeadUpdate, db: AsyncSession = Depends(get_db)):
    lead = await lead_service.update_lead(db, lead_id, data)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@router.delete("/{lead_id}", status_code=204)
async def delete_lead(lead_id: int, db: AsyncSession = Depends(get_db)):
    deleted = await lead_service.delete_lead(db, lead_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Lead not found")
