from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("New password must be at least 8 characters")
        return v


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
