from datetime import datetime

from pydantic import BaseModel, EmailStr


class LeadCreate(BaseModel):
    name: str
    email: EmailStr
    phone: str | None = None
    company: str | None = None
    title: str | None = None
    source: str | None = None
    apollo_id: str | None = None
    status: str = "new"
    enrichment_data: dict | None = None


class LeadUpdate(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    company: str | None = None
    title: str | None = None
    source: str | None = None
    apollo_id: str | None = None
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
    apollo_id: str | None
    status: str
    score: int | None
    enrichment_data: dict | None
    enrichment_status: str
    score_details: dict | None
    ai_analysis: dict | None
    ai_analyzed_at: datetime | None
    ai_status: str | None
    created_at: datetime
    updated_at: datetime


class LeadListResponse(BaseModel):
    items: list[LeadResponse]
    total: int
    limit: int
    offset: int


class EnrichmentLogResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    provider: str
    raw_response: dict | None
    success: bool
    created_at: datetime


class RoutingLogResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    destination: str
    payload: dict | None
    response_code: int | None
    success: bool
    error: str | None
    created_at: datetime


class LeadDetailResponse(LeadResponse):
    enrichment_logs: list[EnrichmentLogResponse]
    routing_logs: list[RoutingLogResponse]


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
