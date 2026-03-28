import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.schemas.lead import LeadResponse


class CompanyCreate(BaseModel):
    name: str
    domain: str | None = None
    website: str | None = None
    industry: str | None = None
    employee_count: int | None = None
    location_city: str | None = None
    location_state: str | None = None
    location_country: str | None = None
    apollo_id: str | None = None
    funding_stage: str | None = None
    annual_revenue_range: str | None = None
    tech_stack: list[str] | None = None
    keywords: list[str] | None = None
    linkedin_url: str | None = None
    founded_year: int | None = None
    abm_status: str | None = "target"


class CompanyUpdate(BaseModel):
    name: str | None = None
    domain: str | None = None
    website: str | None = None
    industry: str | None = None
    employee_count: int | None = None
    location_city: str | None = None
    location_state: str | None = None
    location_country: str | None = None
    apollo_id: str | None = None
    funding_stage: str | None = None
    annual_revenue_range: str | None = None
    tech_stack: list[str] | None = None
    keywords: list[str] | None = None
    linkedin_url: str | None = None
    founded_year: int | None = None
    abm_status: str | None = None


class CompanyResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    client_id: int
    name: str
    domain: str | None
    website: str | None
    industry: str | None
    employee_count: int | None
    location_city: str | None
    location_state: str | None
    location_country: str | None
    apollo_id: str | None
    funding_stage: str | None
    annual_revenue_range: str | None
    tech_stack: list[str] | None
    keywords: list[str] | None
    linkedin_url: str | None
    founded_year: int | None
    enrichment_data: dict | None
    enrichment_status: str
    enriched_at: datetime | None
    abm_status: str
    created_at: datetime
    updated_at: datetime
    lead_count: int = 0
    custom_fields: dict[str, Any] = {}

    @model_validator(mode="after")
    def _extract_custom_fields(self) -> "CompanyResponse":
        self.custom_fields = (self.enrichment_data or {}).get("custom_fields") or {}
        return self


class CompanyDetailResponse(CompanyResponse):
    leads: list[LeadResponse] = []


class ContactPullRequest(BaseModel):
    titles: list[str] = []
    seniorities: list[str] = []
    limit: int = Field(default=25, ge=1, le=100)


class CompanyBulkUploadResponse(BaseModel):
    created: int
    updated: int
    skipped: int
    errors: list[str]
