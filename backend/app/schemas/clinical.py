from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.models.enums import ClinicalKind
from app.schemas.base import ReadMixin


class ClinicalEntryBase(BaseModel):
    kind: ClinicalKind
    reference_product: str | None = None
    summary: str


class ClinicalEntryCreate(ClinicalEntryBase):
    pass


class ClinicalEntryUpdate(BaseModel):
    kind: ClinicalKind | None = None
    reference_product: str | None = None
    summary: str | None = None


class ClinicalEntryRead(ClinicalEntryBase, ReadMixin):
    product_id: uuid.UUID
