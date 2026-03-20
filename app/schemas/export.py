"""Schemas for lead export endpoints (CSV and Webhook)."""
from datetime import datetime

from pydantic import BaseModel, field_validator

VALID_EXPORT_FIELDS = frozenset({
    "name", "email", "phone", "company", "title", "source",
    "status", "score", "enrichment_status", "apollo_id",
    "linkedin_url", "industry", "employee_count", "location",
    "ai_qualification", "ai_icebreakers", "ai_email_angle",
    "created_at", "enriched_at",
})

DEFAULT_EXPORT_FIELDS: list[str] = [
    "name", "email", "company", "title", "source", "score",
    "status", "created_at",
]

FIELD_LABELS: dict[str, str] = {
    "name": "Full Name",
    "email": "Email",
    "phone": "Phone",
    "company": "Company",
    "title": "Title",
    "source": "Source",
    "status": "Status",
    "score": "Lead Score",
    "enrichment_status": "Enrichment Status",
    "apollo_id": "Apollo ID",
    "linkedin_url": "LinkedIn URL",
    "industry": "Industry",
    "employee_count": "Employees",
    "location": "Location",
    "ai_qualification": "AI Qualification",
    "ai_icebreakers": "AI Icebreakers",
    "ai_email_angle": "AI Email Angle",
    "created_at": "Created Date",
    "enriched_at": "Enriched Date",
}


class LeadFilters(BaseModel):
    source: str | None = None
    status: str | None = None
    score_min: int | None = None
    score_max: int | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    search: str | None = None


class ExportRequest(BaseModel):
    filters: LeadFilters = LeadFilters()
    fields: list[str] = DEFAULT_EXPORT_FIELDS

    @field_validator("fields")
    @classmethod
    def validate_fields(cls, v: list[str]) -> list[str]:
        if not v:
            return list(DEFAULT_EXPORT_FIELDS)
        invalid = [f for f in v if f not in VALID_EXPORT_FIELDS]
        if invalid:
            raise ValueError(
                f"Invalid export fields: {invalid}. "
                f"Valid values: {sorted(VALID_EXPORT_FIELDS)}"
            )
        return v


class WebhookExportRequest(BaseModel):
    webhook_url: str
    filters: LeadFilters = LeadFilters()
    batch_size: int = 50
    include_enrichment: bool = True
    include_ai_analysis: bool = False

    @field_validator("webhook_url")
    @classmethod
    def validate_webhook_url(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith("https://"):
            raise ValueError("webhook_url must start with https://")
        from urllib.parse import urlparse
        parsed = urlparse(v)
        if not parsed.netloc:
            raise ValueError("webhook_url must be a valid URL with a hostname")
        return v

    @field_validator("batch_size")
    @classmethod
    def validate_batch_size(cls, v: int) -> int:
        if v < 1 or v > 200:
            raise ValueError("batch_size must be between 1 and 200")
        return v


class WebhookExportResponse(BaseModel):
    export_id: str
    total_leads: int
    total_batches: int
    status: str
    webhook_url: str  # masked — domain only
