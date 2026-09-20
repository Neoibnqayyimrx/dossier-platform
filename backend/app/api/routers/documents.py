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

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db, require_project_owner
from app.core.storage import get_storage_client
from app.ctd.region_profiles import get_region_profile
from app.ctd.structure import MODULE_2_5_FOLDERS, repeatable_section_numbers
from app.documents.ingest import (
    UnsupportedDocumentError,
    ingest_document,
    versioned_storage_key_for,
)
from app.models import DocumentVersion, Project, SectionDocument, User
from app.target_toc import target_leaves_by_number
from app.templating.registry import SECTIONS

# Same bound, same reasoning, as the sequence-number retry in projects.py:
# enough to absorb a double-click or two tabs, not enough for a pathological
# loop to hold a worker open.
_VERSION_NUMBER_MAX_ATTEMPTS = 5


async def _next_version_number(db: AsyncSession, document: SectionDocument) -> int:
    """The next free version number for this leaf.

    max() + 1 rather than count() + 1, for the reason the sequence numbers
    use it too: a deleted version must not free its number for reuse. A
    version number names a historical fact, and two different files having
    been "version 3" at different times is not a history.

    A document that has never been saved has no id yet, so there is nothing
    to query and this is its first version.
    """
    if document.id is None:
        return 1
    highest = await db.scalar(
        select(func.max(DocumentVersion.version_number)).where(
            DocumentVersion.section_document_id == document.id
        )
    )
    return (highest or 0) + 1


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


class DocumentVersionRead(BaseModel):
    """One entry in a leaf's history (P26).

    Carries `md5` deliberately: "did this actually change, or was the same
    file uploaded twice?" is the first question anyone reading a version
    list asks, and comparing checksums answers it without downloading
    anything.
    """

    id: uuid.UUID
    version_number: int
    original_filename: str
    content_type: str
    size_bytes: int
    md5: str
    uploaded_at: datetime
    uploaded_by_id: uuid.UUID | None
    storage_key: str
    is_current: bool

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

    PUT, not POST, because the leaf is the resource and it holds exactly
    one CURRENT document: uploading twice replaces what the package will
    ship. Since P26 it no longer destroys what it replaced -- every upload
    also appends a `document_version` row with its own bytes, so the
    history of a leaf between two sequences is recoverable.
    """
    region = await db.scalar(select(Project.region).where(Project.id == project_id))
    _assert_attachable(region, section_number, subject_slug)

    data = await file.read()
    instance_key = f"{section_number}-{subject_slug}" if subject_slug else section_number

    # selectinload, not a plain select: appending to `document.versions`
    # below would otherwise lazy-load the collection, and a lazy load on
    # the async engine raises MissingGreenlet -- the same trap this
    # codebase has now met five times.
    existing = await db.scalar(
        select(SectionDocument)
        .where(
            SectionDocument.project_id == project_id,
            SectionDocument.section_number == section_number,
            SectionDocument.subject_slug == subject_slug,
        )
        .options(selectinload(SectionDocument.versions))
    )
    document = existing or SectionDocument(
        project_id=project_id,
        section_number=section_number,
        subject_slug=subject_slug,
    )

    for attempt in range(_VERSION_NUMBER_MAX_ATTEMPTS):
        version_number = await _next_version_number(db, document)

        try:
            ingested = ingest_document(
                project_id=project_id,
                instance_key=instance_key,
                data=data,
                content_type=file.content_type or "",
                filename=file.filename or instance_key,
                storage=get_storage_client(),
                # Each version at its own key, so replacing a document does
                # not overwrite the bytes of the one it replaced.
                storage_key=versioned_storage_key_for(project_id, instance_key, version_number),
            )
        except UnsupportedDocumentError as exc:
            # 422, not 400: the request is well-formed, the FILE is the
            # problem, and the message says what to do about it.
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

        original_filename = file.filename or f"{instance_key}.pdf"
        uploaded_at = datetime.now(timezone.utc)

        # The denormalised current-version columns. Every consumer of an
        # uploaded leaf reads these (assemble.py, the lifecycle resolver,
        # the validation rules), which is exactly why they stay here rather
        # than moving behind the version row -- see the model docstring.
        document.storage_key = ingested.storage_key
        document.md5 = ingested.md5
        document.size_bytes = ingested.size_bytes
        document.content_type = ingested.content_type
        document.original_filename = original_filename
        document.uploaded_by_id = user.id
        document.uploaded_at = uploaded_at

        document.versions.append(
            DocumentVersion(
                version_number=version_number,
                storage_key=ingested.storage_key,
                md5=ingested.md5,
                size_bytes=ingested.size_bytes,
                original_filename=original_filename,
                content_type=ingested.content_type,
                uploaded_by_id=user.id,
                uploaded_at=uploaded_at,
            )
        )

        db.add(document)
        try:
            await db.commit()
        except IntegrityError:
            # Two concurrent uploads to the same leaf both read the same
            # max() and both claimed this version number. Identical
            # reasoning, and identical fix, to the sequence-number race
            # closed in gap Phase 1: the constraint is the guarantee, the
            # retry is the recovery. The losing upload's bytes are already
            # in storage under a key nothing references, which is wasteful
            # but harmless -- far better than two rows claiming to be
            # version 3.
            await db.rollback()
            if attempt == _VERSION_NUMBER_MAX_ATTEMPTS - 1:
                raise HTTPException(
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    "Could not allocate a document version due to concurrent uploads; "
                    "please retry.",
                ) from None
            existing = await db.scalar(
                select(SectionDocument)
                .where(
                    SectionDocument.project_id == project_id,
                    SectionDocument.section_number == section_number,
                    SectionDocument.subject_slug == subject_slug,
                )
                .options(selectinload(SectionDocument.versions))
            )
            document = existing or document
            continue

        await db.refresh(document)
        return document

    raise HTTPException(  # pragma: no cover - the loop returns or raises above
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "Could not allocate a document version; please retry.",
    )


async def _document_or_404(
    db: AsyncSession, project_id: uuid.UUID, section_number: str, subject_slug: str
) -> SectionDocument:
    document = await db.scalar(
        select(SectionDocument)
        .where(
            SectionDocument.project_id == project_id,
            SectionDocument.section_number == section_number,
            SectionDocument.subject_slug == subject_slug,
        )
        .options(selectinload(SectionDocument.versions))
    )
    if document is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"No document is attached at {section_number} in this project.",
        )
    return document


@router.get("/{section_number}/versions", response_model=list[DocumentVersionRead])
async def list_document_versions(
    project_id: uuid.UUID,
    section_number: str,
    subject_slug: str = "",
    db: AsyncSession = Depends(get_db),
    _owned: None = Depends(require_project_owner),
) -> list[DocumentVersionRead]:
    """Every file that has ever stood at this leaf, oldest first (P26).

    Oldest first because this is a history and a history reads forwards;
    the caller wanting "the current one" has `is_current` on each entry
    rather than having to know which end of the list to look at.
    """
    document = await _document_or_404(db, project_id, section_number, subject_slug)
    current = document.versions[-1].id if document.versions else None
    return [
        DocumentVersionRead(
            **{
                field: getattr(version, field)
                for field in DocumentVersionRead.model_fields
                if field != "is_current"
            },
            is_current=version.id == current,
        )
        for version in document.versions
    ]


@router.get("/{section_number}/versions/{version_number}/content")
async def download_document_version(
    project_id: uuid.UUID,
    section_number: str,
    version_number: int,
    subject_slug: str = "",
    db: AsyncSession = Depends(get_db),
    _owned: None = Depends(require_project_owner),
) -> Response:
    """The bytes of one historical version.

    WHY this reads the key off the version ROW rather than rebuilding it
    from the arguments: the row is the record of where those bytes were
    actually put. Reconstructing the path would silently return the wrong
    file the day the key convention changes, and a document endpoint
    handing back the wrong document is the worst failure this system has.
    """
    document = await _document_or_404(db, project_id, section_number, subject_slug)
    version = next(
        (
            candidate
            for candidate in document.versions
            if candidate.version_number == version_number
        ),
        None,
    )
    if version is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"{section_number} has no version {version_number} in this project.",
        )

    try:
        data = get_storage_client().get(version.storage_key)
    except Exception as exc:  # storage providers raise different types
        # A version row whose bytes are gone is a broken promise, not a
        # missing document: say so rather than implying it never existed.
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"The stored bytes for version {version_number} are no longer retrievable.",
        ) from exc

    return Response(
        content=data,
        media_type=version.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{version.original_filename}"',
            # So a caller can verify they got the version they asked for.
            "Content-MD5": version.md5,
        },
    )


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
