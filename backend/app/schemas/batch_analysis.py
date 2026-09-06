"""Batch analysis schemas (3.2.S.4.4, 3.2.P.5.4).

Same owner-from-the-path rule as the specification schemas: a batch is
created under `/apis/{id}/batches` or `/products/{id}/batches`, and the
payload cannot name its own owner.
"""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel

from app.models.enums import SpecificationOwnerKind
from app.schemas.base import ReadMixin


class BatchAnalysisResultBase(BaseModel):
    # The specification test this result answers. REQUIRED, and the reason
    # is the whole point of the model: there is no way to record a result
    # for a test that is not in the specification, because there would be
    # no id to send. The API additionally checks that the test belongs to
    # the same owner as the batch -- see app/api/routers/batches.py.
    specification_test_id: uuid.UUID
    result: str
    sort_order: int = 0


class BatchAnalysisResultCreate(BatchAnalysisResultBase):
    pass


class BatchAnalysisResultUpdate(BaseModel):
    result: str | None = None
    sort_order: int | None = None


class BatchAnalysisResultRead(BatchAnalysisResultBase, ReadMixin):
    batch_analysis_id: uuid.UUID


class BatchAnalysisBase(BaseModel):
    batch_number: str
    manufacture_date: date | None = None
    batch_size: str | None = None
    manufacturer_id: uuid.UUID | None = None
    purpose: str | None = None
    notes: str | None = None


class BatchAnalysisCreate(BatchAnalysisBase):
    pass


class BatchAnalysisUpdate(BaseModel):
    batch_number: str | None = None
    manufacture_date: date | None = None
    batch_size: str | None = None
    manufacturer_id: uuid.UUID | None = None
    purpose: str | None = None
    notes: str | None = None


class BatchAnalysisRead(BatchAnalysisBase, ReadMixin):
    active_ingredient_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None
    owner_kind: SpecificationOwnerKind
    # Nested read-only, like ActiveIngredient.specification: a caller
    # fetching a batch essentially always wants the results with it -- a
    # batch with no results is not a batch analysis, it is a batch number.
    results: list[BatchAnalysisResultRead] = []
