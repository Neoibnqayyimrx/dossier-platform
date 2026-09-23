"""Platform account administration ACROSS organizations (gap Phase 6a).

The user's decision for this phase: a super-admin exists, "for accounts
only". It creates organizations (each with its first admin, so none is
born locked out), lists every account, and changes any account's role or
active status -- which is how an organization whose only admin left, or
locked themselves out, gets back in.

What it cannot do is the point of the design: no route here returns a
Product, a Project or a document, and no dossier route anywhere checks
`is_superadmin`. Account administration is not a data bypass -- the line
the global ADMIN held from P14b onwards, kept.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_superadmin
from app.api.routers.admin import apply_update, create_account
from app.models import Organization, User
from app.models.enums import UserRole
from app.schemas.user import OrganizationCreate, OrganizationRead, UserRead, UserUpdate

router = APIRouter(
    prefix="/superadmin", tags=["superadmin"], dependencies=[Depends(require_superadmin)]
)


def _organization_read(organization: Organization, member_count: int) -> OrganizationRead:
    return OrganizationRead(
        id=organization.id,
        created_at=organization.created_at,
        updated_at=organization.updated_at,
        name=organization.name,
        member_count=member_count,
    )


@router.get("/organizations", response_model=list[OrganizationRead])
async def list_organizations(db: AsyncSession = Depends(get_db)) -> list[OrganizationRead]:
    members = (
        select(User.organization_id, func.count(User.id).label("n"))
        .group_by(User.organization_id)
        .subquery()
    )
    rows = await db.execute(
        select(Organization, func.coalesce(members.c.n, 0))
        .outerjoin(members, members.c.organization_id == Organization.id)
        .order_by(Organization.name)
    )
    return [_organization_read(organization, count) for organization, count in rows.all()]


@router.post("/organizations", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
async def create_organization(
    payload: OrganizationCreate, db: AsyncSession = Depends(get_db)
) -> OrganizationRead:
    organization = Organization(name=payload.name)
    db.add(organization)
    await db.flush()
    await create_account(
        db,
        email=payload.admin_email,
        password=payload.admin_password,
        role=UserRole.ADMIN,
        organization_id=organization.id,
    )
    await db.commit()
    await db.refresh(organization)
    return _organization_read(organization, 1)


@router.get("/users", response_model=list[UserRead])
async def list_all_users(db: AsyncSession = Depends(get_db)) -> list[User]:
    stmt = select(User).order_by(User.created_at)
    return list((await db.scalars(stmt)).all())


@router.patch("/users/{user_id}", response_model=UserRead)
async def update_any_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    superadmin: User = Depends(require_superadmin),
) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    apply_update(user, payload, superadmin)
    await db.commit()
    await db.refresh(user)
    return user
