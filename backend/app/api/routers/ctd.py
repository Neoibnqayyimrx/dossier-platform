"""CTD package build endpoint (P08): POST /projects/{id}/build/ctd."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_project_owner
from app.api.overrides import active_overrides
from app.api.loading import READINESS_LOAD_OPTIONS
from app.assembly.assemble import AssemblyBlockedError
from app.ctd.build import build_ctd_package
from app.models import Project
from app.schemas.ctd import CtdBuildResponse, OverrideSummaryRead, PackagedFileRead

router = APIRouter(
    prefix="/projects/{project_id}",
    tags=["ctd"],
    dependencies=[Depends(require_project_owner)],
)


@router.post("/build/ctd", response_model=CtdBuildResponse, status_code=status.HTTP_201_CREATED)
async def build_ctd(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> CtdBuildResponse:
    stmt = select(Project).where(Project.id == project_id).options(*READINESS_LOAD_OPTIONS)
    project = await db.scalar(stmt)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")

    overrides = await active_overrides(db, project_id)
    overridden = frozenset(o.rule_id for o in overrides)

    try:
        result = await build_ctd_package(db, project, overridden_rule_ids=overridden)
    except AssemblyBlockedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    return CtdBuildResponse(
        storage_key=result.storage_key,
        files=[PackagedFileRead(path=f.path, md5=f.md5) for f in result.manifest],
        overrides=[OverrideSummaryRead(rule_id=o.rule_id, reason=o.reason) for o in overrides],
    )
