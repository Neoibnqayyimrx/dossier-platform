from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.models.enums import Region
from app.schemas.applicant import ApplicantRead
from app.schemas.base import ReadMixin
from app.schemas.declaration import DeclarationRead
from app.schemas.product import ProductRead
from app.schemas.sequence import SequenceRead


class ProjectBase(BaseModel):
    name: str
    region: Region = Region.NAFDAC


class ProjectCreate(ProjectBase):
    product_id: uuid.UUID  # Project attaches to existing Product master data
    applicant_id: uuid.UUID | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    region: Region | None = None
    product_id: uuid.UUID | None = None
    applicant_id: uuid.UUID | None = None


class ProjectRead(ProjectBase, ReadMixin):
    product: ProductRead
    sequences: list[SequenceRead] = []
    # Module 1 (P15a): R14 blocks export without an applicant and R16
    # without the required declarations, so the UI has to be able to see
    # both without a second round-trip per project.
    applicant: ApplicantRead | None = None
    declarations: list[DeclarationRead] = []
