"""Validation/readiness endpoints (P06): run the deterministic rule engine
over a project and gate export on the result, with a logged human-override
escape hatch for a specific rule (AGENTS.md §5 -- errors block unless a
human override with a logged reason exists)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_project_owner
from app.api.overrides import active_override_rule_ids, active_overrides
from app.api.loading import READINESS_LOAD_OPTIONS
from app.ctd.naming import ich_name
from app.ectd.report import SequenceNotBuiltError, validate_ectd_sequence
from app.models import Project, Sequence, User, ValidationOverride
from app.validation.report_pdf import build_validation_report_pdf
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


@router.get(
    "/validation-report",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def get_validation_report(
    project_id: uuid.UUID,
    sequence_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """The findings as a PDF someone can read, forward and file (gap
    Phase 5b).

    Without `sequence_id`: the readiness findings -- the data rules the
    Validation tab shows. With it: that built sequence's consolidated eCTD
    validation, the same four layers POST /validate/ectd returns. Either
    way the findings are exactly those the JSON endpoints return; the
    report renders, it does not judge (app/validation/report_pdf.py).
    """
    project = await _get_project_or_404(project_id, db)
    overrides = await active_overrides(db, project_id)
    overridden = frozenset(o.rule_id for o in overrides)

    if sequence_id is None:
        report = run_all(project)
        scope, suffix = "Data rules (readiness)", ""
    else:
        sequence = await db.scalar(
            select(Sequence).where(Sequence.id == sequence_id, Sequence.project_id == project_id)
        )
        if sequence is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Sequence not found on this project")
        try:
            report = await validate_ectd_sequence(db, project, sequence)
        except SequenceNotBuiltError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
        scope = f"eCTD sequence {sequence.number} -- data rules, eCTD checks, external validator, AI reviewer"
        suffix = f"-sequence-{sequence.number}"

    pdf = build_validation_report_pdf(
        project=project,
        scope=scope,
        findings=report.findings,
        is_exportable=report.is_exportable(overridden),
        waived=[(o.rule_id, o.reason) for o in overrides],
        generated_at=datetime.now(timezone.utc),
    )
    filename = f"validation-report-{ich_name(project.product.brand_name)}{suffix}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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
