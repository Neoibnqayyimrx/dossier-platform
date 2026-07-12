from __future__ import annotations

from pydantic import BaseModel, EmailStr

from app.schemas.base import ReadMixin


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserRead(ReadMixin):
    email: str
    is_active: bool


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
