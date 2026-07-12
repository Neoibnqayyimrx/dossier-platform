from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.models.enums import GMPStatus, ManufacturerRole
from app.schemas.base import ReadMixin


class ManufacturerBase(BaseModel):
    name: str
    role: ManufacturerRole
    site_address: str | None = None
    country: str | None = None
    gmp_status: GMPStatus | None = None
    who_gmp: bool = False
    pic_s: bool = False
    manufacturing_licence: str | None = None


class ManufacturerCreate(ManufacturerBase):
    pass


class ManufacturerUpdate(BaseModel):
    name: str | None = None
    role: ManufacturerRole | None = None
    site_address: str | None = None
    country: str | None = None
    gmp_status: GMPStatus | None = None
    who_gmp: bool | None = None
    pic_s: bool | None = None
    manufacturing_licence: str | None = None


class ManufacturerRead(ManufacturerBase, ReadMixin):
    product_id: uuid.UUID
