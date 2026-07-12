from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.models.enums import PackagingComponent
from app.schemas.base import ReadMixin


class PackagingBase(BaseModel):
    component: PackagingComponent
    description: str
    material: str | None = None
    artwork_ref: str | None = None


class PackagingCreate(PackagingBase):
    pass


class PackagingUpdate(BaseModel):
    component: PackagingComponent | None = None
    description: str | None = None
    material: str | None = None
    artwork_ref: str | None = None


class PackagingRead(PackagingBase, ReadMixin):
    product_id: uuid.UUID
