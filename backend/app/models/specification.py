"""SpecificationTest: one row of a specification table, whoever owns it.

A specification is not a sentence, it is a **table**. Every row is a
commitment the manufacturer makes to the regulator and is held to at
release and on stability: *this test*, by *this method*, must meet *this
acceptance criterion*. The free-text field this replaced
(`ActiveIngredient.specifications`) could hold "Assay 90.0-120.0%, related
substances per BP monograph" -- readable, but nothing could check it, cite
a method against it, or render it as the table 3.2.S.4.1 is required to
contain. It was a note about a specification, not a specification.

P13 built this table foreign-keyed to `active_ingredient`, which made it
drug-substance-only by construction, and said so in this docstring: "when
3.2.P.5 is built, the honest move is to widen this table with a nullable
product_id (or extract a shared Specification parent), not to have guessed
today." **P20 is that day**, and it took the first of the two options.

The owner is now one of three: a drug substance (3.2.S.4.1), an excipient
(3.2.P.4.1) or the finished product (3.2.P.5.1) -- three nullable foreign
keys with a CHECK that exactly one is set. See app/models/spec_owner.py for
the full reasoning and for the discriminator-column alternative that was
rejected.

WHY it still repeats per drug substance and per excipient: 3.2.S is
repeated PER SUBSTANCE, so a fixed-dose combination has one complete
specification per active -- ampicillin's assay limits are not
cloxacillin's -- and 3.2.P.4.1 is repeated per excipient for the same
reason. Only the drug product has exactly one specification, because there
is exactly one finished product.

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
from app.models.enums import SpecificationOwnerKind
from app.models.spec_owner import SpecificationOwned, exactly_one_owner

if TYPE_CHECKING:
    from app.models.active_ingredient import ActiveIngredient
    from app.models.batch_analysis import BatchAnalysisResult
    from app.models.excipient import Excipient
    from app.models.product import Product


class SpecificationTest(Base, SpecificationOwned):
    __tablename__ = "specification_test"

    __owner_kinds__ = (
        SpecificationOwnerKind.DRUG_SUBSTANCE,
        SpecificationOwnerKind.DRUG_PRODUCT,
        SpecificationOwnerKind.EXCIPIENT,
    )
    __table_args__ = (exactly_one_owner("ck_specification_test_one_owner", *__owner_kinds__),)

    # NULLABLE now, where P13 made it required. The migration widens rather
    # than replaces: every existing row keeps the exact foreign key it had,
    # so P13's drug-substance behaviour and its tests are untouched.
    active_ingredient_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("active_ingredient.id"), nullable=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("product.id"), nullable=True)
    excipient_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("excipient.id"), nullable=True
    )

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
    #
    # P20 note: rule R22 now PARSES this string to check batch results
    # against it, which sounds like the argument for structured columns
    # coming back. It is not. The parser is allowed to fail -- an
    # unparseable criterion is reported as unchecked, never as passed --
    # so the text stays authoritative and the parsing stays advisory to it.
    # Structured columns would have made the text derived from the parse,
    # which is the wrong way round: the applicant commits to the sentence.
    acceptance_criterion: Mapped[str] = mapped_column(String(300))
    # Preserves the order the applicant chose. Specification tables are
    # conventionally ordered (description, identification, assay, impurities,
    # ...) and an assessor comparing release to stability data reads them
    # side by side -- so the order is content, not presentation.
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    active_ingredient: Mapped["ActiveIngredient | None"] = relationship(
        back_populates="specification"
    )
    product: Mapped["Product | None"] = relationship(back_populates="specification")
    excipient: Mapped["Excipient | None"] = relationship(back_populates="specification")

    # The results that answer this test, across every batch. Deleting a test
    # deletes them: a result whose test no longer exists is a number with no
    # limit, which is precisely the orphan the FK design exists to prevent.
    results: Mapped[list["BatchAnalysisResult"]] = relationship(
        back_populates="specification_test", cascade="all, delete-orphan"
    )
