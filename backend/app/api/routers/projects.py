"""Project CRUD + the two P02-specific endpoints: sequence auto-numbering
and the readiness placeholder (P06 fills in the real checks)."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.loading import PROJECT_CHILD_OPTIONS
from app.models import Product, Project, Sequence, User
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


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> Project:
    if await db.scalar(select(Product.id).where(Product.id == payload.product_id)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")

    project = Project(**payload.model_dump())
    db.add(project)
    await db.commit()
    return await _get_project_or_404(project.id, db)


@router.get("", response_model=list[ProjectRead])
async def list_projects(db: AsyncSession = Depends(get_db)) -> list[Project]:
    stmt = select(Project).options(*PROJECT_CHILD_OPTIONS)
    return list((await db.scalars(stmt)).all())


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Project:
    return await _get_project_or_404(project_id, db)


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> Project:
    project = await _get_project_or_404(project_id, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    await db.commit()
    return await _get_project_or_404(project_id, db)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
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
    _user: User = Depends(get_current_user),
) -> Sequence:
    """Auto-numbers the next sequence: 0000, then 0001, ... — the transaction
    id is derived state, never client input, same as any other
    regulator-facing identifier (that's why SequenceCreateRequest has no
    `number` field at all)."""
    if await db.scalar(select(Project.id).where(Project.id == project_id)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")

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
    project_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> list[Sequence]:
    if await db.scalar(select(Project.id).where(Project.id == project_id)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    stmt = select(Sequence).where(Sequence.project_id == project_id).order_by(Sequence.number)
    return list((await db.scalars(stmt)).all())


@router.patch("/{project_id}/sequences/{sequence_id}", response_model=SequenceRead)
async def update_sequence(
    project_id: uuid.UUID,
    sequence_id: uuid.UUID,
    payload: SequenceUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> Sequence:
    stmt = select(Sequence).where(
        Sequence.id == sequence_id, Sequence.project_id == project_id
    )
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


@router.get("/{project_id}/readiness")
async def get_readiness(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict:
    """Placeholder: P06's deterministic rule engine fills this in with real
    findings. For now it just confirms the project exists."""
    await _get_project_or_404(project_id, db)
    return {"ready": False, "checks": []}
