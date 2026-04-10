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
    is_active: bool | None = None


class ClientPublicResponse(BaseModel):
    """Returned to all authenticated users. Never includes settings."""

    model_config = {"from_attributes": True}

    id: int
    name: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ClientResponse(ClientPublicResponse):
    """Returned to admins and superadmins. Extends the public response with settings."""

    settings: dict


class ClientListResponse(BaseModel):
    items: list[ClientPublicResponse]
    total: int
