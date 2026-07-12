from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.models.enums import CompendialStatus
from app.schemas.base import ReadMixin


class ActiveIngredientBase(BaseModel):
    inn_name: str
    salt_form: str | None = None
    salt_factor: float = 1.0
    compendial_std: CompendialStatus | None = None
    manufacturer_id: uuid.UUID | None = None
    dmf_number: str | None = None
    cep_number: str | None = None
    retest_period_months: int | None = None
    specifications: str | None = None
    particle_size: str | None = None
    residual_solvents: str | None = None


class ActiveIngredientCreate(ActiveIngredientBase):
    pass


class ActiveIngredientUpdate(BaseModel):
    inn_name: str | None = None
    salt_form: str | None = None
    salt_factor: float | None = None
    compendial_std: CompendialStatus | None = None
    manufacturer_id: uuid.UUID | None = None
    dmf_number: str | None = None
    cep_number: str | None = None
    retest_period_months: int | None = None
    specifications: str | None = None
    particle_size: str | None = None
    residual_solvents: str | None = None


class ActiveIngredientRead(ActiveIngredientBase, ReadMixin):
    product_id: uuid.UUID
