"""Validation/readiness endpoints (P06): run the deterministic rule engine
over a project and gate export on the result, with a logged human-override
escape hatch for a specific rule (AGENTS.md §5 -- errors block unless a
human override with a logged reason exists)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_project_owner
from app.api.overrides import active_override_rule_ids
from app.api.loading import READINESS_LOAD_OPTIONS
from app.models import Project, User, ValidationOverride
from app.schemas.validation import (
    FindingRead,
    ReadinessResponse,
    ValidationOverrideCreate,
    ValidationOverrideRead,
)
import app.validation.rules  # noqa: F401  registers every rule on import
from app.validation.engine import run_all

router = APIRouter(
    prefix="/projects/{project_id}",
    tags=["validation"],
    dependencies=[Depends(require_project_owner)],
)


async def _get_project_or_404(project_id: uuid.UUID, db: AsyncSession) -> Project:
    stmt = select(Project).where(Project.id == project_id).options(*READINESS_LOAD_OPTIONS)
    project = await db.scalar(stmt)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    return project


def _to_override_read(override: ValidationOverride) -> ValidationOverrideRead:
    return ValidationOverrideRead(
        id=str(override.id),
        project_id=str(override.project_id),
        withdrawn_at=override.withdrawn_at,
        withdrawn_by_id=(
            str(override.withdrawn_by_id) if override.withdrawn_by_id is not None else None
        ),
        rule_id=override.rule_id,
        reason=override.reason,
        created_by_id=str(override.created_by_id),
    )


@router.get("/readiness", response_model=ReadinessResponse)
async def get_readiness(
    project_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> ReadinessResponse:
    project = await _get_project_or_404(project_id, db)
    overridden = await active_override_rule_ids(db, project_id)
    report = run_all(project)
    return ReadinessResponse(
        is_exportable=report.is_exportable(overridden),
        findings=[FindingRead(**vars(f)) for f in report.findings],
        overridden_rule_ids=sorted(overridden),
    )


@router.post(
    "/validation-overrides",
    response_model=ValidationOverrideRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_override(
    project_id: uuid.UUID,
    payload: ValidationOverrideCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ValidationOverrideRead:
    override = ValidationOverride(
        project_id=project_id,
        rule_id=payload.rule_id,
        reason=payload.reason,
        created_by_id=user.id,
    )
    db.add(override)
    await db.commit()
    return _to_override_read(override)


@router.post(
    "/validation-overrides/{override_id}:withdraw",
    response_model=ValidationOverrideRead,
)
async def withdraw_override(
    project_id: uuid.UUID,
    override_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ValidationOverrideRead:
    """Retract an override without erasing it.

    WHY not DELETE: the row IS the audit trail. An override that can only
    be created and never taken back makes people avoid recording the
    honest one, and deleting it would destroy the record that a human
    once decided this -- and their reason. Withdrawal is therefore a new
    fact written on the same row; the rule starts blocking export again
    the moment it lands (see active_override_rule_ids).
    """
    stmt = select(ValidationOverride).where(
        ValidationOverride.id == override_id,
        ValidationOverride.project_id == project_id,
    )
    override = await db.scalar(stmt)
    if override is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Override not found")
    if override.withdrawn_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "That override was already withdrawn")

    override.withdrawn_at = datetime.now(timezone.utc)
    override.withdrawn_by_id = user.id
    await db.commit()
    await db.refresh(override)
    return _to_override_read(override)


@router.get("/validation-overrides", response_model=list[ValidationOverrideRead])
async def list_overrides(
    project_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> list[ValidationOverrideRead]:
    stmt = select(ValidationOverride).where(ValidationOverride.project_id == project_id)
    rows = (await db.scalars(stmt)).all()
    return [_to_override_read(row) for row in rows]
