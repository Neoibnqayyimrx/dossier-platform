from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.models.enums import Region
from app.schemas.base import ReadMixin
from app.schemas.product import ProductRead
from app.schemas.sequence import SequenceRead


class ProjectBase(BaseModel):
    name: str
    region: Region = Region.NAFDAC


class ProjectCreate(ProjectBase):
    product_id: uuid.UUID  # Project attaches to existing Product master data


class ProjectUpdate(BaseModel):
    name: str | None = None
    region: Region | None = None
    product_id: uuid.UUID | None = None


class ProjectRead(ProjectBase, ReadMixin):
    product: ProductRead
    sequences: list[SequenceRead] = []
