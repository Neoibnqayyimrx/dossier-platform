"""eCTD sequence build endpoint (P09): POST /projects/{id}/build/ectd.

WHY `sequence_id` is a required query param rather than something this
endpoint invents: P02's `POST /projects/{id}/sequences` already owns
sequence auto-numbering (0000, 0001, ...) -- see app.ectd.build's module
docstring. A caller creates the sequence first, then builds it; the two
concerns (numbering a transaction, building its content) stay separate.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.loading import READINESS_LOAD_OPTIONS
from app.assembly.assemble import AssemblyBlockedError
from app.ectd.build import build_ectd_sequence
from app.models import Project, Sequence, ValidationOverride
from app.schemas.ectd import EctdBuildResponse

router = APIRouter(prefix="/projects/{project_id}", tags=["ectd"])


async def _overridden_rule_ids(db: AsyncSession, project_id: uuid.UUID) -> frozenset[str]:
    stmt = select(ValidationOverride.rule_id).where(ValidationOverride.project_id == project_id)
    return frozenset((await db.scalars(stmt)).all())


@router.post("/build/ectd", response_model=EctdBuildResponse, status_code=status.HTTP_201_CREATED)
async def build_ectd(
    project_id: uuid.UUID, sequence_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> EctdBuildResponse:
    stmt = select(Project).where(Project.id == project_id).options(*READINESS_LOAD_OPTIONS)
    project = await db.scalar(stmt)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")

    sequence = await db.scalar(
        select(Sequence).where(Sequence.id == sequence_id, Sequence.project_id == project_id)
    )
    if sequence is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sequence not found on this project")

    overridden = await _overridden_rule_ids(db, project_id)

    try:
        result = await build_ectd_sequence(
            db, project, sequence, overridden_rule_ids=overridden
        )
    except AssemblyBlockedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except NotImplementedError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    await db.commit()

    return EctdBuildResponse(
        storage_key=result.storage_key,
        sequence_number=result.sequence_number,
        operations=result.operations,
    )
