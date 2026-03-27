from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class LeadCreate(BaseModel):
    name: str = Field(max_length=255)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=50)
    company: str | None = Field(default=None, max_length=255)
    title: str | None = Field(default=None, max_length=255)
    source: str | None = Field(default=None, max_length=100)
    apollo_id: str | None = Field(default=None, max_length=100)
    status: str = Field(default="new", max_length=50)
    enrichment_data: dict | None = None


class LeadUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    company: str | None = Field(default=None, max_length=255)
    title: str | None = Field(default=None, max_length=255)
    source: str | None = Field(default=None, max_length=100)
    apollo_id: str | None = Field(default=None, max_length=100)
    status: str | None = Field(default=None, max_length=50)
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
