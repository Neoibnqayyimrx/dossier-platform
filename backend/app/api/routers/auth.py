"""Auth: register + login. No OAuth providers -- just an account that can
hold a bearer token (AGENTS.md P02: "keep it simple but real"). Every
account registers as UserRole.USER; there is no self-service path to
ADMIN (see app.api.routers.admin's module docstring and
scripts/promote_admin.py).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.schemas.user import Token, UserCreate, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, db: AsyncSession = Depends(get_db)) -> User:
    existing = await db.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    user = User(email=payload.email, hashed_password=hash_password(payload.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> Token:
    # OAuth2PasswordRequestForm's field is named "username" by spec; we treat
    # it as the email since that's this app's login identifier.
    user = await db.scalar(select(User).where(User.email == form_data.username))
    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Token(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserRead)
async def me(user: User = Depends(get_current_user)) -> User:
    """Who the bearer token belongs to -- the frontend has no other way to
    know its own role (see app.api.routers.admin's gate). A JWT here
    carries only a user id (see create_access_token), never a role claim:
    baking the role into the token would let it go stale the moment an
    admin changed it, since nothing forces the holder to log in again.
    Looking it up fresh here means a demotion/deactivation takes effect
    the next time the frontend asks, not only at next login."""
    return user
