from datetime import datetime

from pydantic import BaseModel


class ScoringRuleCreate(BaseModel):
    field: str
    operator: str
    value: str
    points: int
    is_active: bool = True


class ScoringRuleUpdate(BaseModel):
    field: str | None = None
    operator: str | None = None
    value: str | None = None
    points: int | None = None
    is_active: bool | None = None


class ScoringRuleResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    client_id: int
    field: str
    operator: str
    value: str
    points: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ScoringRuleListResponse(BaseModel):
    items: list[ScoringRuleResponse]
    total: int


class ScoringTemplateRule(BaseModel):
    field: str
    operator: str
    value: str
    points: int


class ScoringTemplateResponse(BaseModel):
    name: str
    description: str
    rules: list[ScoringTemplateRule]
