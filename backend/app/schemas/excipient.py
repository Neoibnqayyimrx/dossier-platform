from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.models.enums import CompendialStatus, ExcipientFunction, ExcipientOrigin
from app.schemas.base import ReadMixin


class ExcipientBase(BaseModel):
    name: str
    function: ExcipientFunction | None = None
    grade: str | None = None
    supplier: str | None = None
    compendial_status: CompendialStatus | None = None
    # P19: None means NOT STATED, not "synthetic" -- see ExcipientOrigin.
    origin: ExcipientOrigin | None = None


class ExcipientCreate(ExcipientBase):
    pass


class ExcipientUpdate(BaseModel):
    name: str | None = None
    function: ExcipientFunction | None = None
    grade: str | None = None
    supplier: str | None = None
    compendial_status: CompendialStatus | None = None
    origin: ExcipientOrigin | None = None


class ExcipientRead(ExcipientBase, ReadMixin):
    product_id: uuid.UUID
