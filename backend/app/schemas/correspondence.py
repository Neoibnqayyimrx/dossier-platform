"""Correspondence schemas (P27).

`status` is writable on create as well as update because an item can
legitimately arrive closed -- someone recording last year's letters is
entering history, not opening work. `is_overdue` is read-only and derived:
it is a question about today's date, so storing it would be storing an
answer that goes stale overnight.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.models.enums import (
    CorrespondenceDirection,
    CorrespondenceStatus,
    CorrespondenceType,
)
from app.schemas.base import ReadMixin


class CorrespondenceBase(BaseModel):
    direction: CorrespondenceDirection
    correspondence_type: CorrespondenceType
    subject: str
    received_or_sent_at: datetime
    due_date: date | None = None
    status: CorrespondenceStatus = CorrespondenceStatus.OPEN
    notes: str | None = None
    # Both nullable: correspondence often predates any sequence, and the
    # letter may not have been uploaded yet (see the model's docstring).
    sequence_id: uuid.UUID | None = None
    section_document_id: uuid.UUID | None = None


class CorrespondenceCreate(CorrespondenceBase):
    pass


class CorrespondenceUpdate(BaseModel):
    direction: CorrespondenceDirection | None = None
    correspondence_type: CorrespondenceType | None = None
    subject: str | None = None
    received_or_sent_at: datetime | None = None
    due_date: date | None = None
    status: CorrespondenceStatus | None = None
    notes: str | None = None
    sequence_id: uuid.UUID | None = None
    section_document_id: uuid.UUID | None = None


class CorrespondenceRead(CorrespondenceBase, ReadMixin):
    project_id: uuid.UUID
    # Derived from `due_date` and `status` at read time -- never stored,
    # because "is this late?" is a question about today.
    is_overdue: bool
