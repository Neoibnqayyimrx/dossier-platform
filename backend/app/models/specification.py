"""SpecificationTest: one row of a drug-substance specification table (3.2.S.4.1).

A specification is not a sentence, it is a **table**. Every row is a
commitment the manufacturer makes to the regulator and is held to at
release and on stability: *this test*, by *this method*, must meet *this
acceptance criterion*. The free-text field this replaces
(`ActiveIngredient.specifications`) could hold "Assay 90.0-120.0%, related
substances per BP monograph" -- readable, but nothing could check it, cite
a method against it, or render it as the table 3.2.S.4.1 is required to
contain. It was a note about a specification, not a specification.

WHY the rows live on ActiveIngredient rather than Product: 3.2.S is
repeated PER DRUG SUBSTANCE, so a fixed-dose combination has one complete
specification per active -- ampicillin's assay limits are not
cloxacillin's. The same reason strength lives here (see
active_ingredient.py) and the same reason the 2.3 QOS renders one
structural formula per active.

WHY this is not modelled as the drug-PRODUCT specification too (3.2.P.5.1),
which is the same shape: that owner doesn't exist yet, and a premature
polymorphic owner column would be speculation. When 3.2.P.5 is built, the
honest move is to widen this table with a nullable product_id (or extract
a shared Specification parent), not to have guessed today.

Region-neutral by construction: nothing here is NAFDAC-, FDA-, or
EMA-specific. Module 3 is common across ICH regions (ICH M4Q) -- only
Module 1 is regional -- so these rows serve any target the platform grows.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import String, Integer, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.active_ingredient import ActiveIngredient


class SpecificationTest(Base):
    __tablename__ = "specification_test"

    active_ingredient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("active_ingredient.id"))

    # e.g. "Assay", "Related substances", "Water content", "Residual solvents"
    test_name: Mapped[str] = mapped_column(String(200))
    # The analytical procedure. A CITATION, never the method text itself:
    # "BP monograph", "USP <467>", "In-house method AM-014". Pharmacopoeial
    # monographs are copyrighted (AGENTS.md §5) -- the dossier references
    # them, the knowledge base never ingests them.
    method: Mapped[str] = mapped_column(String(200))
    # The limit as it must appear on the page: "90.0 - 120.0 % w/w",
    # "NMT 1.0 %", "Complies". Kept as text ON PURPOSE: acceptance criteria
    # are genuinely heterogeneous (ranges, one-sided limits, qualitative
    # "Complies", conformance to a reference spectrum), and forcing them
    # into numeric min/max columns would either lose the qualitative ones
    # or fill the table with nulls. The regulator reads this string; the
    # structure that matters for checking is the ROW, not the limit's parts.
    acceptance_criterion: Mapped[str] = mapped_column(String(300))
    # Preserves the order the applicant chose. Specification tables are
    # conventionally ordered (description, identification, assay, impurities,
    # ...) and an assessor comparing release to stability data reads them
    # side by side -- so the order is content, not presentation.
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    active_ingredient: Mapped["ActiveIngredient"] = relationship(back_populates="specification")
