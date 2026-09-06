"""Impurity: the named impurity profile (3.2.S.3.2, 3.2.P.5.5).

## What these sections are for

3.2.S.3.2 lists the impurities that can be present in the drug substance --
from the synthesis (process-related) or from the substance breaking down
(degradation) -- with the limit applied to each and where that limit comes
from. 3.2.P.5.5 does the same for the finished product, where the interest
is almost entirely degradation: what the formulation, the container and the
shelf life let form.

An assessor reads these against the specification tables. The specification
says "Related substances -- any individual: NMT 1.0 %"; the impurity table
says which individuals those are and, crucially, **on what authority each
limit rests** -- a pharmacopoeial monograph, an ICH Q3A/Q3B qualification
threshold, or the applicant's own toxicological justification.

## Why `limit_source` is a first-class field

Because an uncited limit is the query an assessor writes back. "NMT 0.15 %"
is a number; "NMT 0.15 %, BP monograph" is a commitment traceable to a
document. Recording it as data rather than as prose is also what lets rule
R11 -- the pharmacopoeial-version reminder, which until P20 could only see
`compendial_std` on the substance and the excipient -- reach impurity
limits: any impurity whose limit is sourced from a pharmacopoeia is a limit
that can change with the next edition, and the platform can say so without
ever storing a word of the monograph itself (AGENTS.md 5).

## Structure, where known

`smiles` is optional and, like `ActiveIngredient.smiles`, is public
chemistry rather than copyrighted text -- so it can be rendered as a real 2D
structure. Many impurities are identified only by a relative retention time
and have no structure to give; that is the ordinary case, and the column is
nullable to say so rather than to invite a guess.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import ImpurityType, SpecificationOwnerKind
from app.models.spec_owner import SpecificationOwned, exactly_one_owner

if TYPE_CHECKING:
    from app.models.active_ingredient import ActiveIngredient
    from app.models.product import Product


class Impurity(Base, SpecificationOwned):
    __tablename__ = "impurity"

    # Two owners, not three: the CTD has an impurity section for the drug
    # substance and one for the drug product, and none for an excipient.
    # See app/models/spec_owner.py on declaring the narrower space.
    __owner_kinds__ = (
        SpecificationOwnerKind.DRUG_SUBSTANCE,
        SpecificationOwnerKind.DRUG_PRODUCT,
    )
    __table_args__ = (exactly_one_owner("ck_impurity_one_owner", *__owner_kinds__),)

    active_ingredient_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("active_ingredient.id"), nullable=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("product.id"), nullable=True)

    # The name an assessor can look up: "Impurity A", "6-Aminopenicillanic
    # acid", "Amoxicillin dimer". Pharmacopoeias letter their named
    # impurities, and citing that letter alongside the chemical name is the
    # convention -- both go here, as one string, because that is how it
    # appears on the page.
    name: Mapped[str] = mapped_column(String(200))
    impurity_type: Mapped[ImpurityType] = mapped_column(SAEnum(ImpurityType))
    # As it must read on the page: "NMT 1.0 %", "NMT 0.15 %". Text, for the
    # same reason acceptance criteria are text (see specification.py).
    limit: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # WHERE the limit comes from: "BP monograph", "ICH Q3A qualification
    # threshold", "In-house, toxicologically justified". A citation, never
    # the source's text.
    limit_source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Public chemistry, never a copyrighted depiction -- same basis as
    # ActiveIngredient.smiles. Null is the ordinary case: an impurity known
    # only by relative retention time has no structure to state.
    smiles: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Where it comes from, in one sentence: "Hydrolysis of the beta-lactam
    # ring", "Residual starting material". This is the ONE genuinely
    # narrative field on the row, and it is the applicant's claim, not the
    # LLM's -- 3.2.S.3.2 is registered as a generated section for exactly
    # that reason.
    origin: Mapped[str | None] = mapped_column(Text, nullable=True)

    active_ingredient: Mapped["ActiveIngredient | None"] = relationship(back_populates="impurities")
    product: Mapped["Product | None"] = relationship(back_populates="impurities")
