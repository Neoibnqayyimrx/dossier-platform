"""Attaching real files to the dossier's leaves (P18).

WHY this router exists: MinIO has been wired in since P04, but only
BUILDERS ever wrote to it, and `artifacts.py` is download-only. There was no
route by which a regulatory affairs officer could put the actual CPP into
the package -- so a quarter of every dossier this platform produced was a
placeholder saying, in capitals, that it was a placeholder.

WHY the storage key is never accepted from the client: `artifacts.py`
already wrote this reasoning down, and it applies with more force to a
write. `StorageClient.put` will happily overwrite ANY key it is given, so a
client-supplied key is a route to writing over another project's built
package -- or another project's uploaded certificate. The key is computed
server-side from the project id and the leaf
(`app/documents/ingest.py::storage_key_for`), and `require_project_owner`
decides whether this caller may touch the project at all.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_project_owner
from app.core.storage import get_storage_client
from app.ctd.region_profiles import get_region_profile
from app.ctd.structure import MODULE_2_5_FOLDERS, repeatable_section_numbers
from app.documents.ingest import UnsupportedDocumentError, ingest_document
from app.models import Project, SectionDocument, User
from app.target_toc import target_leaves_by_number
from app.templating.registry import SECTIONS

router = APIRouter(
    prefix="/projects/{project_id}/documents",
    tags=["documents"],
    dependencies=[Depends(require_project_owner)],
)


class SectionDocumentRead(BaseModel):
    id: uuid.UUID
    section_number: str
    subject_slug: str
    original_filename: str
    content_type: str
    size_bytes: int
    md5: str
    uploaded_at: datetime
    # The key the download endpoint wants. Returned rather than reconstructed
    # in the frontend, so the path convention stays server-side knowledge.
    storage_key: str

    model_config = {"from_attributes": True}


def _assert_attachable(region, section_number: str, subject_slug: str) -> None:
    """Refuse a leaf this platform could not actually place.

    WHY check at UPLOAD instead of discovering it at build time: a file with
    no declared folder cannot go in the package, and `folder_for_section`
    raises rather than inventing a path (its own docstring explains why).
    Accepting the upload anyway would store bytes, show the user a green
    tick, and then fail the build days later -- the exact "looks complete,
    is not" failure this phase exists to remove.
    """
    if section_number not in target_leaves_by_number():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Section {section_number!r} is not a leaf of the target table of contents.",
        )

    if subject_slug:
        # A per-subject leaf is placeable only if it has a per-subject
        # folder -- "3.2.S.3.1 for ampicillin" and "3.2.S.3.1" are different
        # paths, and only the former is right once a product has two actives.
        # P19: asked of every repeat axis, not only the drug substance.
        placeable = section_number in repeatable_section_numbers()
    else:
        placeable = (
            section_number in MODULE_2_5_FOLDERS
            or section_number in SECTIONS
            # Module 1 placement is regional, so it comes from the profile
            # rather than the shared folder map.
            or get_region_profile(region).document_slot(section_number) is not None
        )
    if not placeable:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Section {section_number!r} has no declared folder, so an uploaded file "
            "could not be placed in the package. Map it before attaching one.",
        )


@router.get("", response_model=list[SectionDocumentRead])
async def list_documents(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[SectionDocument]:
    stmt = (
        select(SectionDocument)
        .where(SectionDocument.project_id == project_id)
        .order_by(SectionDocument.section_number, SectionDocument.subject_slug)
    )
    return list((await db.scalars(stmt)).all())


@router.put("/{section_number}", response_model=SectionDocumentRead)
async def upload_document(
    project_id: uuid.UUID,
    section_number: str,
    subject_slug: str = "",
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SectionDocument:
    """Attach (or replace) the document at one leaf.

    PUT, not POST, because the leaf is the resource and it holds exactly one
    document: uploading twice replaces, it does not accumulate. That is a
    deliberate simplification -- see the P18 build-log entry on why there is
    no version history yet, and what would change our mind.
    """
    region = await db.scalar(select(Project.region).where(Project.id == project_id))
    _assert_attachable(region, section_number, subject_slug)

    data = await file.read()
    instance_key = f"{section_number}-{subject_slug}" if subject_slug else section_number

    try:
        ingested = ingest_document(
            project_id=project_id,
            instance_key=instance_key,
            data=data,
            content_type=file.content_type or "",
            filename=file.filename or instance_key,
            storage=get_storage_client(),
        )
    except UnsupportedDocumentError as exc:
        # 422, not 400: the request is well-formed, the FILE is the problem,
        # and the message says what to do about it.
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    existing = await db.scalar(
        select(SectionDocument).where(
            SectionDocument.project_id == project_id,
            SectionDocument.section_number == section_number,
            SectionDocument.subject_slug == subject_slug,
        )
    )
    document = existing or SectionDocument(
        project_id=project_id,
        section_number=section_number,
        subject_slug=subject_slug,
    )
    document.storage_key = ingested.storage_key
    document.md5 = ingested.md5
    document.size_bytes = ingested.size_bytes
    document.content_type = ingested.content_type
    document.original_filename = file.filename or f"{instance_key}.pdf"
    document.uploaded_by_id = user.id
    document.uploaded_at = datetime.now(timezone.utc)

    db.add(document)
    await db.commit()
    await db.refresh(document)
    return document


@router.delete("/{section_number}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    project_id: uuid.UUID,
    section_number: str,
    subject_slug: str = "",
    db: AsyncSession = Depends(get_db),
) -> None:
    """Detach a document, putting the leaf back to a placeholder.

    The stored object is deliberately NOT deleted from object storage. A
    detach is usually "I attached the wrong file", and the cost of keeping
    orphaned bytes is a little storage, while the cost of deleting the
    right file by accident is a document that may not be re-obtainable --
    a CPP takes weeks to reissue.
    """
    document = await db.scalar(
        select(SectionDocument).where(
            SectionDocument.project_id == project_id,
            SectionDocument.section_number == section_number,
            SectionDocument.subject_slug == subject_slug,
        )
    )
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No document attached at that section")
    await db.delete(document)
    await db.commit()
