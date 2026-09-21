"""Sequence schemas.

`status` is readable but NOT writable through SequenceUpdate (P27): it
moves only through the dedicated status endpoint, which enforces the legal
transitions. A status settable by ordinary PATCH would let any caller
record a sequence that went straight from DRAFT to APPROVED, which is the
exact history the enum exists to make unrepresentable.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import SequenceStatus, SubmissionUnitType
from app.schemas.base import ReadMixin


class SequenceBase(BaseModel):
    number: str
    description: str | None = None
    submitted_at: datetime | None = None
    # Freely editable, unlike `status`: this is a declaration of intent
    # about what the sequence IS, which the filer may revise while it is
    # still being prepared. It is not a claim about what has happened.
    submission_unit_type: SubmissionUnitType = SubmissionUnitType.INITIAL


class SequenceCreate(SequenceBase):
    pass


class SequenceUpdate(BaseModel):
    number: str | None = None
    description: str | None = None
    submitted_at: datetime | None = None
    submission_unit_type: SubmissionUnitType | None = None


class SequenceStatusUpdate(BaseModel):
    """The only way to move a sequence's status."""

    status: SequenceStatus


class SequenceRead(SequenceBase, ReadMixin):
    project_id: uuid.UUID
    status: SequenceStatus
