"""Admin-only user management (P14b): list every account, change a role,
deactivate/reactivate one. Not a bypass of the ownership check (P14a) --
an admin still reaches Products/Projects the same way anyone does, through
owner_id. This is account administration, nothing else.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin
from app.models import User
from app.schemas.user import UserRead, UserUpdate

router = APIRouter(prefix="/admin/users", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("", response_model=list[UserRead])
async def list_users(db: AsyncSession = Depends(get_db)) -> list[User]:
    stmt = select(User).order_by(User.created_at)
    return list((await db.scalars(stmt)).all())


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> User:
    # Self-lockout guard: without it, an admin could demote or deactivate
    # their own account here with no way back except direct DB access --
    # possibly the only admin there is.
    if user_id == admin.id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Cannot change your own role or active status"
        )

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    await db.commit()
    await db.refresh(user)
    return user
