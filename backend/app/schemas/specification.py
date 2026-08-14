from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.schemas.base import ReadMixin


class SpecificationTestBase(BaseModel):
    test_name: str
    method: str
    acceptance_criterion: str
    sort_order: int = 0
    notes: str | None = None


class SpecificationTestCreate(SpecificationTestBase):
    pass


class SpecificationTestUpdate(BaseModel):
    test_name: str | None = None
    method: str | None = None
    acceptance_criterion: str | None = None
    sort_order: int | None = None
    notes: str | None = None


class SpecificationTestRead(SpecificationTestBase, ReadMixin):
    active_ingredient_id: uuid.UUID
