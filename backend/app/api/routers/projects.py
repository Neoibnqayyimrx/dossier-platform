"""Project CRUD + sequence auto-numbering (P02). Readiness/validation-
override endpoints live in app.api.routers.validation (P06)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_project_owner
from app.api.loading import PROJECT_CHILD_OPTIONS
from app.ctd.region_profiles import REGION_PROFILES
from app.models import Applicant, Product, Project, Sequence, User
from app.models.enums import ALLOWED_SEQUENCE_TRANSITIONS, SequenceStatus
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from app.schemas.sequence import SequenceRead, SequenceStatusUpdate, SequenceUpdate

router = APIRouter(prefix="/projects", tags=["projects"])

# Each retry costs one extra max() read; a handful is plenty to absorb
# realistic contention (a user double-clicking, two tabs) without letting a
# pathological loop hold a worker open indefinitely.
_SEQUENCE_NUMBER_MAX_ATTEMPTS = 5


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


async def _assert_owns_product(db: AsyncSession, product_id: uuid.UUID, user: User) -> None:
    """Owned, not merely existing: pointing a Project at someone else's
    Product would let you read and edit that product's whole tree through
    the project, defeating the ownership check on every other route."""
    owned = await db.scalar(
        select(Product.id).where(Product.id == product_id, Product.owner_id == user.id)
    )
    if owned is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")


async def _assert_owns_applicant(db: AsyncSession, applicant_id: uuid.UUID, user: User) -> None:
    """Same reasoning for the applicant (P15a): an Applicant carries its own
    owner_id, and naming someone else's on your project would expose their
    company and contact details through this project's reads."""
    owned = await db.scalar(
        select(Applicant.id).where(Applicant.id == applicant_id, Applicant.owner_id == user.id)
    )
    if owned is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Applicant not found")


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Project:
    await _assert_owns_product(db, payload.product_id, user)
    if payload.applicant_id is not None:
        await _assert_owns_applicant(db, payload.applicant_id, user)

    project = Project(**payload.model_dump())
    db.add(project)
    await db.commit()
    return await _get_project_or_404(project.id, db)


@router.get("", response_model=list[ProjectRead])
async def list_projects(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> list[Project]:
    stmt = (
        select(Project)
        .join(Product, Project.product_id == Product.id)
        .where(Product.owner_id == user.id)
        .options(*PROJECT_CHILD_OPTIONS)
    )
    return list((await db.scalars(stmt)).all())


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _owned: None = Depends(require_project_owner),
) -> Project:
    return await _get_project_or_404(project_id, db)


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    _owned: None = Depends(require_project_owner),
) -> Project:
    project = await _get_project_or_404(project_id, db)

    # WHY re-check on update and not only on create: both of these are
    # re-pointable FKs. Moving a project onto someone else's product would
    # silently hand it away (the ownership gate joins through Product, so
    # the caller would lose the project too); naming someone else's
    # applicant would leak their details through this project's reads.
    fields = payload.model_dump(exclude_unset=True)
    if fields.get("product_id") is not None:
        await _assert_owns_product(db, fields["product_id"], user)
    if fields.get("applicant_id") is not None:
        await _assert_owns_applicant(db, fields["applicant_id"], user)

    for field, value in fields.items():
        setattr(project, field, value)
    await db.commit()
    return await _get_project_or_404(project_id, db)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _owned: None = Depends(require_project_owner),
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
    _owned: None = Depends(require_project_owner),
) -> Sequence:
    """Auto-numbers the next sequence: 0000, then 0001, ... — the transaction
    id is derived state, never client input, same as any other
    regulator-facing identifier (that's why SequenceCreateRequest has no
    `number` field at all).

    gap Phase 4b: where the count STARTS is the region's to say. FDA's
    conformance guide says to "begin with sequence number 0001"; ICH's own
    example, the EU and our NAFDAC packages start at 0000. Read from
    `RegionProfile.first_sequence_number`, so the endpoint never asks which
    agency it is talking to.

    WHY the retry loop: read-then-insert is not atomic. Two concurrent POSTs
    can both read max()=0002 and both try to write 0003. The unique
    constraint on (project_id, number) makes the database reject the loser,
    and we then re-read and try again with the number that is now actually
    free. This is the portable fix: a Postgres advisory lock would serialize
    writers more directly, but the test suite runs on SQLite as well as
    Postgres (see tests/conftest.py), and a guarantee that only holds on one
    backend is not a guarantee.
    """
    region = await db.scalar(select(Project.region).where(Project.id == project_id))
    profile = REGION_PROFILES.get(region)
    first_number = profile.first_sequence_number if profile is not None else "0000"

    for _ in range(_SEQUENCE_NUMBER_MAX_ATTEMPTS):
        # max(), not count(): stays correct even if a sequence is ever
        # removed, since the transaction id must never be reused.
        highest = await db.scalar(
            select(func.max(Sequence.number)).where(Sequence.project_id == project_id)
        )
        next_number = f"{int(highest) + 1:04d}" if highest is not None else first_number

        sequence = Sequence(
            project_id=project_id,
            number=next_number,
            description=payload.description,
            submitted_at=payload.submitted_at,
        )
        db.add(sequence)
        try:
            await db.commit()
        except IntegrityError:
            # Someone else took this number between our read and our write.
            # Roll back to clear the failed transaction, then recompute --
            # the next max() read sees their row, so the retry asks for a
            # genuinely new number rather than colliding again.
            await db.rollback()
            continue
        await db.refresh(sequence)
        return sequence

    # Only reachable under sustained contention. Better a 503 the client can
    # retry than a number we are not certain is unique.
    raise HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "Could not allocate a sequence number due to concurrent submissions; please retry.",
    )


@router.get("/{project_id}/sequences", response_model=list[SequenceRead])
async def list_sequences(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _owned: None = Depends(require_project_owner),
) -> list[Sequence]:
    stmt = select(Sequence).where(Sequence.project_id == project_id).order_by(Sequence.number)
    return list((await db.scalars(stmt)).all())


@router.patch("/{project_id}/sequences/{sequence_id}/status", response_model=SequenceRead)
async def update_sequence_status(
    project_id: uuid.UUID,
    sequence_id: uuid.UUID,
    payload: SequenceStatusUpdate,
    db: AsyncSession = Depends(get_db),
    _owned: None = Depends(require_project_owner),
) -> Sequence:
    """Move a sequence to the next legal status.

    WHY this is its own endpoint rather than a field on the ordinary PATCH
    (P27): a status that any PATCH can set is a status that can record a
    history which never happened -- DRAFT straight to APPROVED, or a
    rejection quietly reopened. The ORDER is the information. Putting the
    transition behind its own route is what lets the rule be enforced in
    exactly one place, and lets a refusal say what was actually possible.

    Setting a sequence to its CURRENT status is accepted as a no-op rather
    than refused: it is idempotent, which a client retrying a request
    after a dropped response depends on.
    """
    sequence = await db.scalar(
        select(Sequence).where(Sequence.id == sequence_id, Sequence.project_id == project_id)
    )
    if sequence is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sequence not found")

    target = payload.status
    if target is not sequence.status:
        allowed = ALLOWED_SEQUENCE_TRANSITIONS[sequence.status]
        if target not in allowed:
            # 409, not 422: the request is perfectly well-formed and the
            # value is a real status. What makes it wrong is the state the
            # sequence is in, which is a conflict, not a validation error.
            legal = ", ".join(sorted(status_.value for status_ in allowed)) or "nothing"
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"A sequence that is {sequence.status.value} cannot become "
                f"{target.value}. From here it can only become: {legal}.",
            )
        sequence.status = target

        # WHY the timestamp is set here and not left to the caller: a
        # sequence marked SUBMITTED with no submission date is a record
        # that cannot answer the one question it exists to answer. Only
        # filled if absent, so a filer back-entering a real historical
        # date is not overwritten by today's.
        if target is SequenceStatus.SUBMITTED and sequence.submitted_at is None:
            sequence.submitted_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(sequence)
    return sequence


@router.patch("/{project_id}/sequences/{sequence_id}", response_model=SequenceRead)
async def update_sequence(
    project_id: uuid.UUID,
    sequence_id: uuid.UUID,
    payload: SequenceUpdate,
    db: AsyncSession = Depends(get_db),
    _owned: None = Depends(require_project_owner),
) -> Sequence:
    stmt = select(Sequence).where(Sequence.id == sequence_id, Sequence.project_id == project_id)
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
