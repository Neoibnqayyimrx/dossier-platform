from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from app.models.enums import FDAApplicationType, Region, SubmissionType
from app.schemas.applicant import ApplicantRead
from app.schemas.base import ReadMixin
from app.schemas.declaration import DeclarationRead
from app.schemas.product import ProductRead
from app.schemas.sequence import SequenceRead


class ProjectBase(BaseModel):
    name: str
    region: Region = Region.NAFDAC
    # P17: how much of the CTD this filing owes. Defaults to the one scope
    # the platform was built against, so every existing client keeps
    # working without sending a field it has never heard of.
    submission_type: SubmissionType = SubmissionType.MULTISOURCE_GENERIC
    # gap Phase 4b: the agency-assigned application number and, for FDA,
    # what kind of application it numbers. Free text here because the field
    # is not FDA-specific; FDA's six-digit rule is R34's to enforce, where
    # the message can say which agency wants what.
    application_number: str | None = Field(default=None, max_length=40)
    fda_application_type: FDAApplicationType | None = None


class ProjectCreate(ProjectBase):
    product_id: uuid.UUID  # Project attaches to existing Product master data
    applicant_id: uuid.UUID | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    region: Region | None = None
    submission_type: SubmissionType | None = None
    product_id: uuid.UUID | None = None
    applicant_id: uuid.UUID | None = None
    application_number: str | None = Field(default=None, max_length=40)
    fda_application_type: FDAApplicationType | None = None


class ProjectRead(ProjectBase, ReadMixin):
    product: ProductRead
    sequences: list[SequenceRead] = []
    # Module 1 (P15a): R14 blocks export without an applicant and R16
    # without the required declarations, so the UI has to be able to see
    # both without a second round-trip per project.
    applicant: ApplicantRead | None = None
    declarations: list[DeclarationRead] = []
    # Answers to the conditional sections' yes/no questions, keyed by
    # section number. Read-only here: they are written through
    # PATCH /projects/{id}/conditions, which validates each number against
    # the region profile's applicability table first.
    condition_answers: dict[str, bool] = {}
