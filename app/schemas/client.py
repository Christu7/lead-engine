from datetime import datetime

from pydantic import BaseModel


class ClientCreate(BaseModel):
    name: str
    description: str | None = None
    settings: dict = {}


class ClientUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    settings: dict | None = None


class ClientResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    name: str
    description: str | None
    is_active: bool
    settings: dict
    created_at: datetime
    updated_at: datetime


class ClientListResponse(BaseModel):
    items: list[ClientResponse]
    total: int
