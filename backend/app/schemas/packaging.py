from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.models.enums import PackagingComponent, PackagingRole
from app.schemas.base import ReadMixin


class PackagingBase(BaseModel):
    # P19: which material this row packs. Defaulted rather than required so
    # every existing client keeps working, and defaulted to DRUG_PRODUCT
    # because that is what every row written before the field existed meant
    # -- 3.2.S.6 had nowhere to be filed at the time.
    role: PackagingRole = PackagingRole.DRUG_PRODUCT
    # Set only on a drug-substance pack, and only when a combination
    # product's actives ship differently (see the model).
    active_ingredient_id: uuid.UUID | None = None
    component: PackagingComponent
    description: str
    material: str | None = None
    artwork_ref: str | None = None


class PackagingCreate(PackagingBase):
    pass


class PackagingUpdate(BaseModel):
    role: PackagingRole | None = None
    active_ingredient_id: uuid.UUID | None = None
    component: PackagingComponent | None = None
    description: str | None = None
    material: str | None = None
    artwork_ref: str | None = None


class PackagingRead(PackagingBase, ReadMixin):
    product_id: uuid.UUID
