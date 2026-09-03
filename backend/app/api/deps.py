"""Shared FastAPI dependencies: DB session and the authenticated user.

WHY re-export get_session as get_db here rather than import it directly in
every router: routers should depend on app.api.deps, not reach into
app.core.db — that's the seam tests use to swap in a throwaway database
(see tests/conftest.py's dependency_overrides).
"""

from __future__ import annotations

import uuid

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.security import decode_access_token
from app.models import Product, Project, User
from app.models.enums import UserRole

get_db = get_session

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        user_id = decode_access_token(token)
    except (jwt.PyJWTError, ValueError):
        raise unauthorized

    user = await db.scalar(select(User).where(User.id == user_id))
    if user is None or not user.is_active:
        raise unauthorized
    return user


async def require_project_owner(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Gate for every router mounted entirely under
    `/projects/{project_id}/...` (ctd, ectd, artifacts, validation,
    narrative) -- added as one line on each APIRouter's `dependencies=`
    rather than repeated per-endpoint. 404, not 403: a project belonging
    to someone else should look indistinguishable from one that doesn't
    exist, not confirm its existence to a user who can't touch it.

    Ownership is Product's (see Product.owner_id's WHY), so this joins
    through Project.product_id rather than looking at Project itself.
    """
    stmt = (
        select(Project.id)
        .join(Product, Project.product_id == Product.id)
        .where(Project.id == project_id, Product.owner_id == user.id)
    )
    if await db.scalar(stmt) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """Gate for app.api.routers.admin -- 403, not 404: unlike a project you
    don't own, there's no reason to hide that /admin exists from a logged-in
    user who simply isn't one."""
    if user.role != UserRole.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    return user
