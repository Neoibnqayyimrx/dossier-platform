"""Project CRUD + sequence auto-numbering (P02). Readiness/validation-
override endpoints live in app.api.routers.validation (P06)."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_project_owner
from app.api.loading import PROJECT_CHILD_OPTIONS
from app.models import Applicant, Product, Project, Sequence, User
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from app.schemas.sequence import SequenceRead, SequenceUpdate

router = APIRouter(prefix="/projects", tags=["projects"])


class SequenceCreateRequest(BaseModel):
    """Unlike app.schemas.sequence.SequenceCreate, this has no `number` field
    — the whole point of this endpoint is that the number is server-derived,
    never client input (see create_sequence below)."""

    description: str | None = None
    submitted_at: datetime | None = None


async def _get_project_or_404(project_id: uuid.UUID, db: AsyncSession) -> Project:
    stmt = select(Project).where(Project.id == project_id).options(*PROJECT_CHILD_OPTIONS)
    project = await db.scalar(stmt)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    return project


async def _assert_owns_product(db: AsyncSession, product_id: uuid.UUID, user: User) -> None:
    """Owned, not merely existing: pointing a Project at someone else's
    Product would let you read and edit that product's whole tree through
    the project, defeating the ownership check on every other route."""
    owned = await db.scalar(
        select(Product.id).where(Product.id == product_id, Product.owner_id == user.id)
    )
    if owned is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")


async def _assert_owns_applicant(db: AsyncSession, applicant_id: uuid.UUID, user: User) -> None:
    """Same reasoning for the applicant (P15a): an Applicant carries its own
    owner_id, and naming someone else's on your project would expose their
    company and contact details through this project's reads."""
    owned = await db.scalar(
        select(Applicant.id).where(Applicant.id == applicant_id, Applicant.owner_id == user.id)
    )
    if owned is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Applicant not found")


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Project:
    await _assert_owns_product(db, payload.product_id, user)
    if payload.applicant_id is not None:
        await _assert_owns_applicant(db, payload.applicant_id, user)

    project = Project(**payload.model_dump())
    db.add(project)
    await db.commit()
    return await _get_project_or_404(project.id, db)


@router.get("", response_model=list[ProjectRead])
async def list_projects(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> list[Project]:
    stmt = (
        select(Project)
        .join(Product, Project.product_id == Product.id)
        .where(Product.owner_id == user.id)
        .options(*PROJECT_CHILD_OPTIONS)
    )
    return list((await db.scalars(stmt)).all())


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _owned: None = Depends(require_project_owner),
) -> Project:
    return await _get_project_or_404(project_id, db)


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    _owned: None = Depends(require_project_owner),
) -> Project:
    project = await _get_project_or_404(project_id, db)

    # WHY re-check on update and not only on create: both of these are
    # re-pointable FKs. Moving a project onto someone else's product would
    # silently hand it away (the ownership gate joins through Product, so
    # the caller would lose the project too); naming someone else's
    # applicant would leak their details through this project's reads.
    fields = payload.model_dump(exclude_unset=True)
    if fields.get("product_id") is not None:
        await _assert_owns_product(db, fields["product_id"], user)
    if fields.get("applicant_id") is not None:
        await _assert_owns_applicant(db, fields["applicant_id"], user)

    for field, value in fields.items():
        setattr(project, field, value)
    await db.commit()
    return await _get_project_or_404(project_id, db)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _owned: None = Depends(require_project_owner),
) -> None:
    project = await _get_project_or_404(project_id, db)
    await db.delete(project)
    await db.commit()


@router.post(
    "/{project_id}/sequences", response_model=SequenceRead, status_code=status.HTTP_201_CREATED
)
async def create_sequence(
    project_id: uuid.UUID,
    payload: SequenceCreateRequest,
    db: AsyncSession = Depends(get_db),
    _owned: None = Depends(require_project_owner),
) -> Sequence:
    """Auto-numbers the next sequence: 0000, then 0001, ... — the transaction
    id is derived state, never client input, same as any other
    regulator-facing identifier (that's why SequenceCreateRequest has no
    `number` field at all)."""
    # max(), not count(): stays correct even if a sequence is ever removed,
    # since the transaction id must never be reused.
    highest = await db.scalar(
        select(func.max(Sequence.number)).where(Sequence.project_id == project_id)
    )
    next_number = f"{(int(highest) + 1) if highest is not None else 0:04d}"

    sequence = Sequence(
        project_id=project_id,
        number=next_number,
        description=payload.description,
        submitted_at=payload.submitted_at,
    )
    db.add(sequence)
    await db.commit()
    await db.refresh(sequence)
    return sequence


@router.get("/{project_id}/sequences", response_model=list[SequenceRead])
async def list_sequences(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _owned: None = Depends(require_project_owner),
) -> list[Sequence]:
    stmt = select(Sequence).where(Sequence.project_id == project_id).order_by(Sequence.number)
    return list((await db.scalars(stmt)).all())


@router.patch("/{project_id}/sequences/{sequence_id}", response_model=SequenceRead)
async def update_sequence(
    project_id: uuid.UUID,
    sequence_id: uuid.UUID,
    payload: SequenceUpdate,
    db: AsyncSession = Depends(get_db),
    _owned: None = Depends(require_project_owner),
) -> Sequence:
    stmt = select(Sequence).where(Sequence.id == sequence_id, Sequence.project_id == project_id)
    sequence = await db.scalar(stmt)
    if sequence is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sequence not found")
    # number is server-derived (see create_sequence) and never client-editable.
    updates = payload.model_dump(exclude_unset=True, exclude={"number"})
    for field, value in updates.items():
        setattr(sequence, field, value)
    await db.commit()
    await db.refresh(sequence)
    return sequence
