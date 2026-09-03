from __future__ import annotations

from pydantic import BaseModel, EmailStr

from app.models.enums import UserRole
from app.schemas.base import ReadMixin


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserRead(ReadMixin):
    email: str
    is_active: bool
    role: UserRole


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserUpdate(BaseModel):
    """Admin-only (app.api.routers.admin) -- both fields optional so a
    caller can flip just one without re-sending the other."""

    role: UserRole | None = None
    is_active: bool | None = None
