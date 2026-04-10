from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator


class AdminCreateUser(BaseModel):
    email: EmailStr
    password: str
    name: str | None = None
    role: str = "member"
    client_ids: list[int] = []


class AdminUpdateUserRole(BaseModel):
    role: str


class AdminUpdateUser(BaseModel):
    name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    new_password: str | None = None

    @field_validator("new_password")
    @classmethod
    def password_min_length(cls, v: str | None) -> str | None:
        if v is not None and len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class AdminUserClientInfo(BaseModel):
    id: int
    name: str


class AdminUserResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    email: str
    name: str | None = None
    role: str
    is_active: bool
    clients: list[AdminUserClientInfo] = []
    created_at: datetime
    last_login_at: datetime | None = None


class AdminClientResponse(BaseModel):
    id: int
    name: str
    description: str | None
    is_active: bool
    user_count: int
    lead_count: int
    company_count: int
    created_at: datetime


class AdminUpdateClient(BaseModel):
    name: str | None = None
    description: str | None = None


class AssignClientRequest(BaseModel):
    client_id: int
