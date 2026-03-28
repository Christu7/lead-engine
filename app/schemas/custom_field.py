import re
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_validator, model_validator

FIELD_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
ENRICHMENT_MAPPING_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_.\[\]]*$")
VALID_FIELD_TYPES = frozenset({"text", "number", "date", "boolean", "select"})
VALID_ENTITY_TYPES = frozenset({"lead", "company"})


class CustomFieldDefinitionCreate(BaseModel):
    entity_type: str
    field_key: str
    field_label: str
    field_type: str
    options: list[str] | None = None
    is_required: bool = False
    show_in_table: bool = False
    sort_order: int = 0
    enrichment_source: str | None = None
    enrichment_mapping: str | None = None

    @field_validator("entity_type")
    @classmethod
    def validate_entity_type(cls, v: str) -> str:
        if v not in VALID_ENTITY_TYPES:
            raise ValueError(f"entity_type must be one of: {', '.join(sorted(VALID_ENTITY_TYPES))}")
        return v

    @field_validator("field_key")
    @classmethod
    def validate_field_key(cls, v: str) -> str:
        if len(v) > 100:
            raise ValueError("field_key must be 100 chars or fewer")
        if not FIELD_KEY_RE.match(v):
            raise ValueError(
                "field_key must start with a lowercase letter and contain only "
                "lowercase letters, digits, and underscores"
            )
        return v

    @field_validator("field_type")
    @classmethod
    def validate_field_type(cls, v: str) -> str:
        if v not in VALID_FIELD_TYPES:
            raise ValueError(f"field_type must be one of: {', '.join(sorted(VALID_FIELD_TYPES))}")
        return v

    @field_validator("enrichment_mapping")
    @classmethod
    def validate_enrichment_mapping(cls, v: str | None) -> str | None:
        if v is not None:
            if len(v) > 200:
                raise ValueError("enrichment_mapping must be 200 chars or fewer")
            if not ENRICHMENT_MAPPING_RE.match(v):
                raise ValueError(
                    "enrichment_mapping must start with a letter or underscore and contain "
                    "only letters, digits, underscores, dots, and brackets"
                )
        return v

    @model_validator(mode="after")
    def validate_enrichment_source_required(self) -> "CustomFieldDefinitionCreate":
        if self.enrichment_mapping and not self.enrichment_source:
            raise ValueError("enrichment_source is required when enrichment_mapping is set")
        return self


class CustomFieldDefinitionUpdate(BaseModel):
    field_label: str | None = None
    field_type: str | None = None
    options: list[str] | None = None
    is_required: bool | None = None
    show_in_table: bool | None = None
    sort_order: int | None = None
    enrichment_source: str | None = None
    enrichment_mapping: str | None = None

    @field_validator("field_type")
    @classmethod
    def validate_field_type(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_FIELD_TYPES:
            raise ValueError(f"field_type must be one of: {', '.join(sorted(VALID_FIELD_TYPES))}")
        return v

    @field_validator("enrichment_mapping")
    @classmethod
    def validate_enrichment_mapping(cls, v: str | None) -> str | None:
        if v is not None:
            if len(v) > 200:
                raise ValueError("enrichment_mapping must be 200 chars or fewer")
            if not ENRICHMENT_MAPPING_RE.match(v):
                raise ValueError(
                    "enrichment_mapping must start with a letter or underscore and contain "
                    "only letters, digits, underscores, dots, and brackets"
                )
        return v

    @model_validator(mode="after")
    def validate_enrichment_source_required(self) -> "CustomFieldDefinitionUpdate":
        if self.enrichment_mapping and not self.enrichment_source:
            raise ValueError("enrichment_source is required when enrichment_mapping is set")
        return self


class CustomFieldDefinitionResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    client_id: int
    entity_type: str
    field_key: str
    field_label: str
    field_type: str
    options: list[str] | None
    is_required: bool
    show_in_table: bool
    sort_order: int
    enrichment_source: str | None
    enrichment_mapping: str | None
    created_at: datetime
    updated_at: datetime


class CustomFieldValuesUpdate(BaseModel):
    values: dict[str, Any]
