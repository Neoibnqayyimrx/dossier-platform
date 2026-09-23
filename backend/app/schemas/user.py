from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import UserRole
from app.schemas.base import ORMBase, ReadMixin


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    # gap Phase 6a: registering creates a NEW organization with this account
    # as its admin (see app.api.routers.auth.register). Optional, because a
    # name the person has not thought of yet should not block signing up;
    # the email-based default is what the migration gave existing users.
    organization_name: str | None = Field(default=None, min_length=1, max_length=200)


class OrganizationSummary(ORMBase):
    """Just enough to say WHICH organization -- nested in every UserRead."""

    id: uuid.UUID
    name: str


class UserRead(ReadMixin):
    email: str
    is_active: bool
    role: UserRole
    organization: OrganizationSummary
    is_superadmin: bool


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserUpdate(BaseModel):
    """Admin-only (app.api.routers.admin and .superadmin) -- both fields
    optional so a caller can flip just one without re-sending the other.

    `is_superadmin` is deliberately absent: no API path grants it, the same
    way no API path granted the global ADMIN before gap Phase 6a
    (scripts/promote_admin.py is the one way in)."""

    role: UserRole | None = None
    is_active: bool | None = None


class MemberCreate(BaseModel):
    """An org admin adding a colleague (gap Phase 6a). No organization
    field: a member always joins the ADMIN'S organization, taken from the
    token -- the same reason ProductCreate has no owner field."""

    email: EmailStr
    password: str
    role: UserRole = UserRole.USER


class OrganizationCreate(BaseModel):
    """A super-admin creating an organization together with its first
    admin. Together, because an organization with no admin has nobody who
    can add its members -- it would be born locked out."""

    name: str = Field(min_length=1, max_length=200)
    admin_email: EmailStr
    admin_password: str


class OrganizationRead(ReadMixin):
    name: str
    member_count: int
