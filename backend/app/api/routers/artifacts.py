"""Download a built package (P11c).

P08/P09 put their zips in object storage and return a `storage_key`; until
now nothing could actually hand those bytes to a human. This is that
endpoint.

WHY the key is validated against the project's own prefix rather than
trusted: `key` arrives from the client, and `StorageClient.get` will
happily fetch ANY key it's given. Without the check, a caller could pass
another project's key -- or any object in the bucket -- and read it. The
builders already scope every artifact under `projects/{project_id}/`
(app/ctd/build.py, app/ectd/build.py), so requiring that prefix costs
nothing and closes the hole. This is authorization, not validation: it
must stay even if the key format changes.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.storage import get_storage_client
from app.models import Project, User

router = APIRouter(prefix="/projects/{project_id}", tags=["artifacts"])

ZIP_CONTENT_TYPE = "application/zip"


@router.get("/artifacts")
async def download_artifact(
    project_id: uuid.UUID,
    key: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> Response:
    if await db.scalar(select(Project.id).where(Project.id == project_id)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")

    expected_prefix = f"projects/{project_id}/"
    if not key.startswith(expected_prefix):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "That artifact does not belong to this project",
        )

    storage = get_storage_client()
    try:
        data = storage.get(key)
    except Exception as exc:  # storage providers raise different types
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No such artifact -- has it been built yet?"
        ) from exc

    filename = key.rsplit("/", 1)[-1]
    return Response(
        content=data,
        media_type=ZIP_CONTENT_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
