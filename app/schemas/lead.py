from datetime import datetime

from pydantic import BaseModel, EmailStr


class LeadCreate(BaseModel):
    name: str
    email: EmailStr
    phone: str | None = None
    company: str | None = None
    title: str | None = None
    source: str | None = None
    status: str = "new"
    score: int | None = None
    enrichment_data: dict | None = None
    enrichment_status: str = "pending"


class LeadUpdate(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    company: str | None = None
    title: str | None = None
    source: str | None = None
    status: str | None = None
    score: int | None = None
    enrichment_data: dict | None = None


class LeadResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    client_id: int
    name: str
    email: str
    phone: str | None
    company: str | None
    title: str | None
    source: str | None
    status: str
    score: int | None
    enrichment_data: dict | None
    enrichment_status: str
    score_details: dict | None
    created_at: datetime
    updated_at: datetime


class LeadListResponse(BaseModel):
    items: list[LeadResponse]
    total: int
    limit: int
    offset: int


class BulkImportRow(BaseModel):
    row: int
    errors: list[str]


class BulkImportResponse(BaseModel):
    total: int
    created: int
    updated: int
    skipped: int
    failed: int
    errors: list[BulkImportRow]
