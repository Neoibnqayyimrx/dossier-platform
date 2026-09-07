"""Bioequivalence schemas (5.3.1.2, 5.2, 1.4.1, 1.2.17, 1.2.18).

Same owner-from-the-path rule as every other child collection: a study is
created under `/products/{id}/bioequivalence` and the payload cannot name
its own product. The ownership check the router factory runs is on the
parent in the path, so the path is the only place an owner can be trusted
to come from.

WHY the confidence-interval bounds are `Decimal` on the wire and not
`float`: these three numbers decide whether a product is approvable, and
the acceptance window is written to two decimal places. `float` would let
124.995 arrive as 124.99499999999999 and be compared against 125.00 -- a
rounding artefact deciding a marketing authorisation. Pydantic parses the
JSON number into a Decimal, and the column stores Numeric(7, 2).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import (
    BEDoseRegimen,
    BEFedState,
    BEStudyDesign,
    BiowaiverKind,
    PKParameter,
)
from app.schemas.base import ReadMixin


class ReferenceProductBase(BaseModel):
    name: str
    strength: str | None = None
    dosage_form: str | None = None
    manufacturer: str | None = None
    country_of_origin: str | None = None
    batch_number: str | None = None
    expiry_date: date | None = None
    purchase_country: str | None = None


class ReferenceProductCreate(ReferenceProductBase):
    pass


class ReferenceProductUpdate(BaseModel):
    name: str | None = None
    strength: str | None = None
    dosage_form: str | None = None
    manufacturer: str | None = None
    country_of_origin: str | None = None
    batch_number: str | None = None
    expiry_date: date | None = None
    purchase_country: str | None = None


class ReferenceProductRead(ReferenceProductBase, ReadMixin):
    product_id: uuid.UUID
    # Derived on the model: brand and maker as one comparable string. Sent
    # so the wizard can show what rule R26 will actually compare, rather
    # than leaving the browser to reassemble it and get it subtly different.
    identity: str


class BioequivalenceResultBase(BaseModel):
    parameter: PKParameter
    geometric_mean_ratio: Decimal | None = None
    # Both bounds are REQUIRED. A confidence interval with one end is not a
    # partial result, it is not a confidence interval -- and a rule that
    # checked only the bound it was given would report a clean pass on a
    # study whose other end is at 140 %.
    ci_lower: Decimal
    ci_upper: Decimal
    intra_subject_cv: Decimal | None = None


class BioequivalenceResultCreate(BioequivalenceResultBase):
    pass


class BioequivalenceResultRead(BioequivalenceResultBase, ReadMixin):
    bioequivalence_study_id: uuid.UUID
    sort_order: int = 0


class BioequivalenceStudyBase(BaseModel):
    study_identifier: str
    title: str | None = None
    design: BEStudyDesign
    fed_state: BEFedState
    dose_regimen: BEDoseRegimen
    subjects_enrolled: int | None = None
    subjects_completed: int | None = None
    analyte: str | None = None
    bioanalytical_method: str | None = None
    cro_name: str | None = None
    study_site: str | None = None
    start_date: date | None = None
    completion_date: date | None = None
    # All three cross-references are optional on the wire, like the
    # stability study's axes: a study entered before its comparator or its
    # batch has been recorded is a legitimate half-finished state, and the
    # RULES -- not the schema -- decide whether the dossier can be
    # exported. A schema that refused the intermediate state would make the
    # wizard demand the rows in one particular order.
    reference_product_id: uuid.UUID | None = None
    test_batch_id: uuid.UUID | None = None
    test_batch_size_units: int | None = None
    test_batch_manufacture_date: date | None = None
    notes: str | None = None


class BioequivalenceStudyCreate(BioequivalenceStudyBase):
    pass


class BioequivalenceStudyUpdate(BaseModel):
    study_identifier: str | None = None
    title: str | None = None
    design: BEStudyDesign | None = None
    fed_state: BEFedState | None = None
    dose_regimen: BEDoseRegimen | None = None
    subjects_enrolled: int | None = None
    subjects_completed: int | None = None
    analyte: str | None = None
    bioanalytical_method: str | None = None
    cro_name: str | None = None
    study_site: str | None = None
    start_date: date | None = None
    completion_date: date | None = None
    reference_product_id: uuid.UUID | None = None
    test_batch_id: uuid.UUID | None = None
    test_batch_size_units: int | None = None
    test_batch_manufacture_date: date | None = None
    notes: str | None = None


class BioequivalenceStudyRead(BioequivalenceStudyBase, ReadMixin):
    product_id: uuid.UUID
    # Nested read-only: a bioequivalence study without its confidence
    # intervals is a protocol, not a study.
    results: list[BioequivalenceResultRead] = []
    # Derived. Both are assembled on the model so the screen, the BTI form
    # and the tabular listing describe one study the same way.
    dropouts: int | None = None
    design_summary: str


class BiowaiverBase(BaseModel):
    kind: BiowaiverKind
    strength: str
    bcs_class: int | None = None
    dissolution_similarity_f2: Decimal | None = None
    supporting_study_id: uuid.UUID | None = None
    justification: str | None = None


class BiowaiverCreate(BiowaiverBase):
    pass


class BiowaiverUpdate(BaseModel):
    kind: BiowaiverKind | None = None
    strength: str | None = None
    bcs_class: int | None = None
    dissolution_similarity_f2: Decimal | None = None
    supporting_study_id: uuid.UUID | None = None
    justification: str | None = None


class BiowaiverRead(BiowaiverBase, ReadMixin):
    product_id: uuid.UUID
    # Which leaf this request is filed at, derived on the model so the
    # wizard's biowaiver control and the renderer cannot disagree about
    # whether a BCS waiver is 1.2.17 or 1.2.18.
    section_number: str
