"""Applicant CRUD (P15a): the legal entity submitting a filing.

WHY top-level rather than nested under a project: an Applicant is master
data, like Product. A local agent files a dozen foreign products over the
years and is one legal entity, not a dozen copies -- so it is created
once, listed, and pointed at by Project.applicant_id.

WHY it carries its own owner_id (see the model's WHY): unlike a
certificate or a declaration, it is reached directly rather than through
a Product, so it has no owner to borrow. Every query here filters on it,
and 404 rather than 403 keeps someone else's applicant indistinguishable
from one that never existed -- the same rule as everywhere else.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models import Applicant, User
from app.schemas.applicant import ApplicantCreate, ApplicantRead, ApplicantUpdate

router = APIRouter(prefix="/applicants", tags=["applicants"])


async def _get_applicant_or_404(applicant_id: uuid.UUID, user: User, db: AsyncSession) -> Applicant:
    stmt = select(Applicant).where(Applicant.id == applicant_id, Applicant.owner_id == user.id)
    applicant = await db.scalar(stmt)
    if applicant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Applicant not found")
    return applicant


@router.post("", response_model=ApplicantRead, status_code=status.HTTP_201_CREATED)
async def create_applicant(
    payload: ApplicantCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Applicant:
    # owner_id comes from the token, never the payload -- ApplicantCreate
    # has no such field, so there is nothing for a client to spoof.
    applicant = Applicant(**payload.model_dump(), owner_id=user.id)
    db.add(applicant)
    await db.commit()
    await db.refresh(applicant)
    return applicant


@router.get("", response_model=list[ApplicantRead])
async def list_applicants(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> list[Applicant]:
    stmt = select(Applicant).where(Applicant.owner_id == user.id).order_by(Applicant.company_name)
    return list((await db.scalars(stmt)).all())


@router.get("/{applicant_id}", response_model=ApplicantRead)
async def get_applicant(
    applicant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Applicant:
    return await _get_applicant_or_404(applicant_id, user, db)


@router.patch("/{applicant_id}", response_model=ApplicantRead)
async def update_applicant(
    applicant_id: uuid.UUID,
    payload: ApplicantUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Applicant:
    applicant = await _get_applicant_or_404(applicant_id, user, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(applicant, field, value)
    await db.commit()
    await db.refresh(applicant)
    return applicant


@router.delete("/{applicant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_applicant(
    applicant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    applicant = await _get_applicant_or_404(applicant_id, user, db)
    await db.delete(applicant)
    await db.commit()
