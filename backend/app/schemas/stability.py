"""Stability schemas (3.2.S.7, 3.2.P.8).

Same owner-from-the-path rule as the specification and batch schemas: a
study is created under `/apis/{id}/stability` or
`/products/{id}/stability`, and the payload cannot name its own owner. The
ownership check the router factory runs is on the parent in the path, so
the path is the only place an owner can be trusted to come from.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.models.enums import SpecificationOwnerKind, StabilityStudyType
from app.schemas.base import ReadMixin


class StabilityResultBase(BaseModel):
    # The specification test this result answers. REQUIRED, for the same
    # reason a batch result's is: there is no way to record a stability
    # result for a test that is not in the specification, because there
    # would be no id to send. The API additionally checks that the test
    # belongs to the same material the study is of -- see
    # app/api/routers/stability_results.py.
    specification_test_id: uuid.UUID
    timepoint_months: int
    result: str
    sort_order: int = 0


class StabilityResultCreate(StabilityResultBase):
    pass


class StabilityResultUpdate(BaseModel):
    result: str | None = None
    sort_order: int | None = None


class StabilityResultRead(StabilityResultBase, ReadMixin):
    stability_study_id: uuid.UUID
    # Derived on the model, never stored (see app/models/stability.py).
    # Returned so the grid can mark a cell without the browser having to
    # agree with the backend about what the limit means -- though it also
    # checks locally as you type, which is what makes the flag instant.
    # `null` is a third state and never means "passed".
    meets_criterion: bool | None = None


class StabilityStudyBase(BaseModel):
    study_type: StabilityStudyType
    condition: str
    duration_months: int
    # The three axes P21 added. All optional on the wire: a study whose
    # batch has not been entered yet is a legitimate half-finished state,
    # and the completeness rules -- not the schema -- decide whether the
    # dossier can be exported.
    batch_analysis_id: uuid.UUID | None = None
    packaging_id: uuid.UUID | None = None
    protocol: str | None = None
    notes: str | None = None


class StabilityStudyCreate(StabilityStudyBase):
    pass


class StabilityStudyUpdate(BaseModel):
    study_type: StabilityStudyType | None = None
    condition: str | None = None
    duration_months: int | None = None
    batch_analysis_id: uuid.UUID | None = None
    packaging_id: uuid.UUID | None = None
    protocol: str | None = None
    notes: str | None = None


class StabilityStudyRead(StabilityStudyBase, ReadMixin):
    product_id: uuid.UUID | None = None
    active_ingredient_id: uuid.UUID | None = None
    owner_kind: SpecificationOwnerKind
    # Nested read-only, like BatchAnalysisRead.results: a study without its
    # timepoints is not a stability study, it is a storage condition.
    results: list[StabilityResultRead] = []
    # Derived. The number R05 actually checks a claim against, returned so
    # the wizard can show what the data supports beside what was claimed.
    longest_passing_timepoint: int | None = None
