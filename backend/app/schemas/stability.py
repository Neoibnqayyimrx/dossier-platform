from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.models.enums import StabilityStudyType
from app.schemas.base import ReadMixin


class StabilityStudyBase(BaseModel):
    study_type: StabilityStudyType
    condition: str
    duration_months: int
    protocol: str | None = None
    result_summary: str


class StabilityStudyCreate(StabilityStudyBase):
    pass


class StabilityStudyUpdate(BaseModel):
    study_type: StabilityStudyType | None = None
    condition: str | None = None
    duration_months: int | None = None
    protocol: str | None = None
    result_summary: str | None = None


class StabilityStudyRead(StabilityStudyBase, ReadMixin):
    product_id: uuid.UUID
