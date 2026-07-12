from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.schemas.base import ReadMixin


class BatchFormulaLineBase(BaseModel):
    component: str
    is_active: bool = False
    spec: str
    qty_per_unit_mg: float
    batch_size_units: int
    declared_batch_qty_kg: float | None = None


class BatchFormulaLineCreate(BatchFormulaLineBase):
    pass


class BatchFormulaLineUpdate(BaseModel):
    component: str | None = None
    is_active: bool | None = None
    spec: str | None = None
    qty_per_unit_mg: float | None = None
    batch_size_units: int | None = None
    declared_batch_qty_kg: float | None = None


class BatchFormulaLineRead(BatchFormulaLineBase, ReadMixin):
    product_id: uuid.UUID
