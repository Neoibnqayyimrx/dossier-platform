from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.base import ReadMixin


class SequenceBase(BaseModel):
    number: str
    description: str | None = None
    submitted_at: datetime | None = None


class SequenceCreate(SequenceBase):
    pass


class SequenceUpdate(BaseModel):
    number: str | None = None
    description: str | None = None
    submitted_at: datetime | None = None


class SequenceRead(SequenceBase, ReadMixin):
    project_id: uuid.UUID
