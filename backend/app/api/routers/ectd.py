"""eCTD build (P09) and validation (P10) endpoints:
POST /projects/{id}/build/ectd, POST /projects/{id}/validate/ectd.

WHY `sequence_id` is a required query param on both, rather than something
either endpoint invents: P02's `POST /projects/{id}/sequences` already
owns sequence auto-numbering (0000, 0001, ...) -- see app.ectd.build's
module docstring. A caller creates the sequence, builds it, then
(separately, possibly much later, possibly by someone else) validates
what was built; three concerns, three calls.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_project_owner
from app.api.loading import READINESS_LOAD_OPTIONS
from app.assembly.assemble import AssemblyBlockedError
from app.ectd.build import build_ectd_sequence
from app.ectd.report import SequenceNotBuiltError, validate_ectd_sequence
from app.models import Project, Sequence, ValidationOverride
from app.schemas.ectd import EctdBuildResponse, EctdValidationResponse, FindingRead

router = APIRouter(
    prefix="/projects/{project_id}",
    tags=["ectd"],
    dependencies=[Depends(require_project_owner)],
)


async def _overridden_rule_ids(db: AsyncSession, project_id: uuid.UUID) -> frozenset[str]:
    stmt = select(ValidationOverride.rule_id).where(ValidationOverride.project_id == project_id)
    return frozenset((await db.scalars(stmt)).all())


async def _get_project_and_sequence(
    db: AsyncSession, project_id: uuid.UUID, sequence_id: uuid.UUID
) -> tuple[Project, Sequence]:
    stmt = select(Project).where(Project.id == project_id).options(*READINESS_LOAD_OPTIONS)
    project = await db.scalar(stmt)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")

    sequence = await db.scalar(
        select(Sequence).where(Sequence.id == sequence_id, Sequence.project_id == project_id)
    )
    if sequence is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sequence not found on this project")

    return project, sequence


@router.post("/build/ectd", response_model=EctdBuildResponse, status_code=status.HTTP_201_CREATED)
async def build_ectd(
    project_id: uuid.UUID, sequence_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> EctdBuildResponse:
    project, sequence = await _get_project_and_sequence(db, project_id, sequence_id)
    overridden = await _overridden_rule_ids(db, project_id)

    try:
        result = await build_ectd_sequence(db, project, sequence, overridden_rule_ids=overridden)
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


@router.post("/validate/ectd", response_model=EctdValidationResponse)
async def validate_ectd(
    project_id: uuid.UUID, sequence_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> EctdValidationResponse:
    project, sequence = await _get_project_and_sequence(db, project_id, sequence_id)

    try:
        report = await validate_ectd_sequence(db, project, sequence)
    except SequenceNotBuiltError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    return EctdValidationResponse(
        sequence_number=sequence.number,
        is_exportable=report.is_exportable(),
        findings=[
            FindingRead(
                rule_id=f.rule_id,
                severity=f.severity.value,
                category=f.category,
                message=f.message,
                section=f.section,
                source=f.source,
            )
            for f in report.findings
        ],
    )
