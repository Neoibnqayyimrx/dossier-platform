from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.models.enums import CompendialStatus, ExcipientFunction
from app.schemas.base import ReadMixin


class ExcipientBase(BaseModel):
    name: str
    function: ExcipientFunction | None = None
    grade: str | None = None
    supplier: str | None = None
    compendial_status: CompendialStatus | None = None


class ExcipientCreate(ExcipientBase):
    pass


class ExcipientUpdate(BaseModel):
    name: str | None = None
    function: ExcipientFunction | None = None
    grade: str | None = None
    supplier: str | None = None
    compendial_status: CompendialStatus | None = None


class ExcipientRead(ExcipientBase, ReadMixin):
    product_id: uuid.UUID
