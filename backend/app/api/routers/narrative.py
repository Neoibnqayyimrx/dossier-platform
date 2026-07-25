"""Narrative generation endpoints (P05): generate a draft, then require an
explicit human approve/edit before it's usable (AGENTS.md §5 — "everything
the LLM writes is reviewable"). `:generate`/`:approve`/`:edit` action-style
suffixes (Google Cloud API "custom method" convention) rather than plain
REST verbs, since these aren't CRUD on a resource -- they're state
transitions with side effects (an LLM call; a human review decision)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.api.loading import PROJECT_CHILD_OPTIONS
from app.models import Project, User
from app.models.kb import KBChunk
from app.models.narrative import NarrativeGeneration
from app.narrative.generate import generate_narrative
from app.narrative.guardrails import NarrativeGuardrailError
from app.narrative.review import approve_narrative, edit_narrative
from app.schemas.narrative import NarrativeEditRequest, NarrativeGenerateResponse, NarrativeRead

router = APIRouter(
    prefix="/projects/{project_id}/sections/{section_number}/narrative", tags=["narrative"]
)


async def _get_project_or_404(project_id: uuid.UUID, db: AsyncSession) -> Project:
    stmt = select(Project).where(Project.id == project_id).options(*PROJECT_CHILD_OPTIONS)
    project = await db.scalar(stmt)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    return project


async def _get_narrative_or_404(
    db: AsyncSession, project_id: uuid.UUID, section_number: str, slot: str, narrative_id: uuid.UUID
) -> NarrativeGeneration:
    stmt = (
        select(NarrativeGeneration)
        .options(selectinload(NarrativeGeneration.sources).selectinload(KBChunk.document))
        .where(
            NarrativeGeneration.id == narrative_id,
            NarrativeGeneration.project_id == project_id,
            NarrativeGeneration.section_number == section_number,
            NarrativeGeneration.slot == slot,
        )
    )
    narrative = await db.scalar(stmt)
    if narrative is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Narrative generation not found")
    return narrative


def _to_read(narrative: NarrativeGeneration) -> NarrativeRead:
    return NarrativeRead(
        id=narrative.id,
        created_at=narrative.created_at,
        updated_at=narrative.updated_at,
        project_id=str(narrative.project_id),
        section_number=narrative.section_number,
        slot=narrative.slot,
        model_name=narrative.model_name,
        output=narrative.output,
        warnings=narrative.warnings.split("\n") if narrative.warnings else [],
        status=narrative.status,
        final_text=narrative.final_text,
        sources=[f"{chunk.document.title} {chunk.document.version}" for chunk in narrative.sources],
    )


@router.post(
    "/{slot}:generate",
    response_model=NarrativeGenerateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate(
    project_id: uuid.UUID,
    section_number: str,
    slot: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> NarrativeGenerateResponse:
    project = await _get_project_or_404(project_id, db)
    try:
        result = await generate_narrative(db, project, section_number, slot)
    except NarrativeGuardrailError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    narrative = await _get_narrative_or_404(
        db, project_id, section_number, slot, result.narrative.id
    )
    return NarrativeGenerateResponse(narrative=_to_read(narrative), warnings=result.warnings)


@router.get("/{slot}", response_model=list[NarrativeRead])
async def list_generations(
    project_id: uuid.UUID,
    section_number: str,
    slot: str,
    db: AsyncSession = Depends(get_db),
) -> list[NarrativeRead]:
    stmt = (
        select(NarrativeGeneration)
        .options(selectinload(NarrativeGeneration.sources).selectinload(KBChunk.document))
        .where(
            NarrativeGeneration.project_id == project_id,
            NarrativeGeneration.section_number == section_number,
            NarrativeGeneration.slot == slot,
        )
        .order_by(NarrativeGeneration.created_at)
    )
    rows = (await db.scalars(stmt)).all()
    return [_to_read(row) for row in rows]


@router.post("/{slot}/{narrative_id}:approve", response_model=NarrativeRead)
async def approve(
    project_id: uuid.UUID,
    section_number: str,
    slot: str,
    narrative_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> NarrativeRead:
    narrative = await _get_narrative_or_404(db, project_id, section_number, slot, narrative_id)
    approve_narrative(narrative)
    await db.commit()
    narrative = await _get_narrative_or_404(db, project_id, section_number, slot, narrative_id)
    return _to_read(narrative)


@router.post("/{slot}/{narrative_id}:edit", response_model=NarrativeRead)
async def edit(
    project_id: uuid.UUID,
    section_number: str,
    slot: str,
    narrative_id: uuid.UUID,
    payload: NarrativeEditRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> NarrativeRead:
    narrative = await _get_narrative_or_404(db, project_id, section_number, slot, narrative_id)
    edit_narrative(narrative, payload.text)
    await db.commit()
    narrative = await _get_narrative_or_404(db, project_id, section_number, slot, narrative_id)
    return _to_read(narrative)
