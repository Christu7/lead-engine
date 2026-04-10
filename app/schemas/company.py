import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

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


class ContactPullFilters(BaseModel):
    """Provider-agnostic filters for pulling contacts from a company.

    Provider translation (e.g. Apollo field names) happens exclusively inside
    the provider module. Field names here must not reference any provider API.
    """

    titles: list[str] = Field(
        default_factory=list,
        description="Job title keywords to filter by (e.g. 'VP of Sales').",
    )
    seniorities: list[str] = Field(
        default_factory=list,
        description="Seniority level codes (e.g. 'vp', 'director', 'c_suite').",
    )
    contact_locations: list[str] = Field(
        default_factory=list,
        description="Geographic locations to restrict results to (e.g. 'New York', 'United Kingdom').",
    )
    include_keywords: list[str] = Field(
        default_factory=list,
        description="Keywords that must appear in the contact's profile.",
    )
    exclude_keywords: list[str] = Field(
        default_factory=list,
        description="Keywords that must NOT appear in the contact's profile.",
    )
    limit: int = Field(default=25, ge=1, le=100)

    # ── Per-list length caps ──────────────────────────────────────────────────

    @field_validator("titles")
    @classmethod
    def _cap_titles(cls, v: list[str]) -> list[str]:
        if len(v) > 50:
            raise ValueError("titles may contain at most 50 entries")
        return [t[:200] for t in v]

    @field_validator("seniorities")
    @classmethod
    def _cap_seniorities(cls, v: list[str]) -> list[str]:
        if len(v) > 20:
            raise ValueError("seniorities may contain at most 20 entries")
        return v

    @field_validator("contact_locations")
    @classmethod
    def _cap_locations(cls, v: list[str]) -> list[str]:
        if len(v) > 10:
            raise ValueError("contact_locations may contain at most 10 entries")
        return [loc[:200] for loc in v]

    @field_validator("include_keywords", "exclude_keywords")
    @classmethod
    def _cap_keywords(cls, v: list[str]) -> list[str]:
        if len(v) > 10:
            raise ValueError("keyword lists may contain at most 10 entries")
        return [kw[:100] for kw in v]


# Backward-compatible alias — existing code that imports ContactPullRequest continues to work.
ContactPullRequest = ContactPullFilters


class CompanyBulkUploadResponse(BaseModel):
    created: int
    updated: int
    skipped: int
    errors: list[str]
