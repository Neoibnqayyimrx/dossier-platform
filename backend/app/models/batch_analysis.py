"""BatchAnalysis: real results from real batches (3.2.S.4.4, 3.2.P.5.4).

## What the section is, regulatorily

3.2.S.4.1 and 3.2.P.5.1 say what the material *must* meet. 3.2.S.4.4 and
3.2.P.5.4 show what it *did* meet, batch by batch, for the batches the
applicant is putting forward -- typically the ones used in the stability
studies and the bioequivalence study. An assessor reads the two side by
side, and the question they are asking is exactly one question: **does every
number in the batch table sit inside the limit the specification table
declares?**

That question is arithmetic on data the platform already holds, which is
why this model exists rather than a free-text "batch analysis summary"
field. A summary can say "all batches complied" while the table beneath it
shows an assay of 103.2 % against a 90.0-102.0 % limit; a computed table
cannot.

## Why a result points at a SpecificationTest

`BatchAnalysisResult.specification_test_id` is a real foreign key, not a
test NAME typed again. Two consequences, both deliberate:

1. **A result cannot be recorded for a test that is not in the
   specification.** There is no row to point at, so the mistake is
   unrepresentable rather than merely detectable. The wizard's batch screen
   is a list of the spec's tests for the same reason (P20b).
2. **The limit a result is checked against is never a copy.** Rule R22
   reads `result.specification_test.acceptance_criterion` -- the same string
   3.2.S.4.1 renders. A specification whose limit is tightened tightens the
   check on every batch already on file, with nothing to re-enter.

## Why the batch carries the same three-owner shape as the specification

A batch is a batch OF something: of the drug substance (3.2.S.4.4) or of the
finished product (3.2.P.5.4). It has to be able to name the same owners its
specification can, or the two could not be matched -- and R22's precondition
("this result's test belongs to this batch's owner") would have nothing to
compare. The CTD has no excipient batch-analysis leaf, so `BatchAnalysis`
declares the narrower two-owner space; see app/models/spec_owner.py.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import SpecificationOwnerKind
from app.models.spec_owner import SpecificationOwned, exactly_one_owner

if TYPE_CHECKING:
    from app.models.active_ingredient import ActiveIngredient
    from app.models.manufacturer import Manufacturer
    from app.models.product import Product
    from app.models.specification import SpecificationTest


class BatchAnalysis(Base, SpecificationOwned):
    __tablename__ = "batch_analysis"

    __owner_kinds__ = (
        SpecificationOwnerKind.DRUG_SUBSTANCE,
        SpecificationOwnerKind.DRUG_PRODUCT,
    )
    __table_args__ = (exactly_one_owner("ck_batch_analysis_one_owner", *__owner_kinds__),)

    active_ingredient_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("active_ingredient.id"), nullable=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("product.id"), nullable=True)

    # The batch number as it appears on the certificate of analysis. A
    # STRING, not an integer: batch numbers carry site and year coding
    # ("EX/24/0117"), and an assessor cross-references this exact token
    # against the stability tables and the BE study report.
    batch_number: Mapped[str] = mapped_column(String(80))
    manufacture_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Free text, like `pack_size`: a batch size is "250,000 capsules" or
    # "500 kg" depending on what was made, and the unit is part of the fact.
    batch_size: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # WHERE it was made. A real foreign key when the site is one of the
    # product's own manufacturers -- which is the case that matters, because
    # then 3.2.S.2.1/3.2.P.3.1 and this table cannot name the site
    # differently. Nullable for a batch from a site not otherwise modelled.
    manufacturer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("manufacturer.id"), nullable=True
    )
    # What the batch was FOR, in the applicant's own words: "stability",
    # "bioequivalence study", "process validation". An assessor looks for
    # this because a batch table with no stated purpose does not tell them
    # whether the stability data and the BE data come from the same material.
    purpose: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    active_ingredient: Mapped["ActiveIngredient | None"] = relationship(
        back_populates="batch_analyses"
    )
    product: Mapped["Product | None"] = relationship(back_populates="batch_analyses")
    manufacturer: Mapped["Manufacturer | None"] = relationship(back_populates="batch_analyses")

    results: Mapped[list["BatchAnalysisResult"]] = relationship(
        back_populates="batch_analysis",
        cascade="all, delete-orphan",
        # Ordered by the SPECIFICATION's order, so the batch table's rows
        # line up with the specification table's rows on the assessor's
        # screen. Sorting by anything else -- entry order, test name --
        # would make the two tables have to be read against each other
        # instead of across.
        order_by="BatchAnalysisResult.sort_order",
    )


class BatchAnalysisResult(Base):
    """One measured value, against one specification test, for one batch."""

    __tablename__ = "batch_analysis_result"

    batch_analysis_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("batch_analysis.id"))
    specification_test_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("specification_test.id"))

    # The result AS REPORTED on the certificate of analysis: "99.4 %",
    # "0.12 %", "Complies", "White crystalline powder". Text for the same
    # reason the acceptance criterion is text -- a specification's rows are
    # not all numeric, and a numeric column would have to drop the ones
    # that are not, which are usually the first three rows of the table.
    result: Mapped[str] = mapped_column(String(300))
    # Denormalised from the specification test's `sort_order` at write time
    # so the relationship above can order without a join. WHY that is safe:
    # it is presentation order only -- every check reads the limit through
    # `specification_test`, never through this. If it drifts, a table is out
    # of order; nothing is mis-checked.
    sort_order: Mapped[int] = mapped_column(default=0)

    batch_analysis: Mapped["BatchAnalysis"] = relationship(back_populates="results")
    specification_test: Mapped["SpecificationTest"] = relationship(back_populates="results")
