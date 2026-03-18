from datetime import datetime

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ClientInfo(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    name: str


class UserResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    email: str
    role: str
    active_client_id: int | None
    clients: list[ClientInfo]
    is_active: bool
    created_at: datetime
