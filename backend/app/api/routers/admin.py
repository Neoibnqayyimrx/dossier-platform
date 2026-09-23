"""Organization account management (P14b; scoped to one organization
since gap Phase 6a): an org ADMIN lists their organization's accounts,
adds a colleague, and changes a colleague's role or active status.

Not a bypass of the ownership check -- an admin reaches Products/Projects
the same way any member does, through their organization. This is account
administration, nothing else.

WHY another organization's user is a 404 here, not a 403: the same rule as
every dossier route. An org admin must not be able to learn, by probing
ids, that an account exists in someone else's organization.
Administration ACROSS organizations is the super-admin's
(app.api.routers.superadmin).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin
from app.core.security import hash_password
from app.models import User
from app.models.enums import UserRole
from app.schemas.user import MemberCreate, UserRead, UserUpdate

router = APIRouter(prefix="/admin/users", tags=["admin"], dependencies=[Depends(require_admin)])


async def create_account(
    db: AsyncSession, *, email: str, password: str, role: UserRole, organization_id: uuid.UUID
) -> User:
    """One account, in one organization -- shared with the super-admin's
    "create an organization with its first admin". 409 on a taken email,
    the same answer registration gives."""
    if await db.scalar(select(User.id).where(User.email == email)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = User(
        email=email,
        hashed_password=hash_password(password),
        role=role,
        organization_id=organization_id,
    )
    db.add(user)
    return user


def apply_update(user: User, payload: UserUpdate, acting: User) -> None:
    """Shared by both admin routers.

    Self-lockout guard: without it, an admin could demote or deactivate
    their own account with no way back except direct DB access -- possibly
    the only admin their organization has.
    """
    if user.id == acting.id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Cannot change your own role or active status"
        )
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)


@router.get("", response_model=list[UserRead])
async def list_users(
    db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)
) -> list[User]:
    stmt = (
        select(User).where(User.organization_id == admin.organization_id).order_by(User.created_at)
    )
    return list((await db.scalars(stmt)).all())


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def add_member(
    payload: MemberCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> User:
    """How a colleague joins an organization. The admin sets a first
    password and hands it over; there is no invitation email because the
    platform sends no email at all."""
    user = await create_account(
        db,
        email=payload.email,
        password=payload.password,
        role=payload.role,
        organization_id=admin.organization_id,
    )
    await db.commit()
    await db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> User:
    user = await db.scalar(
        select(User).where(User.id == user_id, User.organization_id == admin.organization_id)
    )
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    apply_update(user, payload, admin)
    await db.commit()
    await db.refresh(user)
    return user
