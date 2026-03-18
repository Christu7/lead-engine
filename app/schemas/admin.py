from datetime import datetime

from pydantic import BaseModel, EmailStr


class AdminCreateUser(BaseModel):
    email: EmailStr
    password: str
    role: str = "member"


class AdminUserResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    email: str
    role: str
    is_active: bool
    created_at: datetime


class AssignClientRequest(BaseModel):
    client_id: int
