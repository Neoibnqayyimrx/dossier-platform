"""Product information: the SmPC, the label and the leaflet as ONE row (P23).

## The defect this table exists to make unbuildable

Leaves 1.3.1, 1.3.2 and 1.3.3 -- the Summary of Product Characteristics,
the outer and inner labels, and the patient information leaflet -- say the
same things to three different audiences. They must agree on strength,
shelf life, storage, pack sizes, indications and contraindications.

In real filings they routinely do not. They are written at different times
by different people, and a shelf-life extension updates two of the three.
It is one of the most commonly raised deficiencies there is, and it is
entirely a *bookkeeping* failure: nobody disagrees about the shelf life,
they just have three copies of it.

So this model holds ONE copy of the things all three documents say, and
the three documents are rendered from it. Divergence between them is not
prevented by a check; it is unrepresentable.

## What is DERIVED and what is AUTHORED, and why the split falls there

**Nothing that already exists elsewhere is a column here.** Strength lives
on `ActiveIngredient`. Shelf life and storage live on `Product` and are
judged against the stability data (rule R05). Pack sizes come from the
`Packaging` rows that 3.2.P.7 is built from. The excipient list is the
`Excipient` collection that 3.2.P.4.1 is built from. Every one of those is
computed at render time by `app.templating.product_information.
shared_values`, which is the single function all three documents read --
see its docstring for the provenance strings it carries.

Putting a `shelf_life_months` column on this table would be the single
worst thing this phase could do. It would make the defect representable
again, and the platform would then need a rule to catch what it had just
finished making impossible.

**What IS authored here is the clinical particulars** -- SmPC sections 4.1
to 4.9 plus 6.2 and 6.6. Those exist nowhere else in the dossier, one
column each rather than one text blob, because the leaflet renders from
the same fields and a blob cannot be re-sectioned for a different reader.

## Why the clinical particulars are DATA and not narrative slots

A therapeutic indication is a *regulatory claim*. So is a
contraindication, and so is a dose. An LLM that drafts "also indicated in
paediatric patients" has invented a marketing authorisation, and the
guardrails in app/narrative/guardrails.py cannot catch it -- there is no
number to leak and no citation to fabricate. AGENTS.md 5's determinism
boundary reads "any value that a regulator cross-checks is produced by
code from the data model, never by the LLM"; an indication is the most
cross-checked value in Module 1.

The prose that IS generated is the leaflet's -- its job is to re-say these
same facts in language a patient can read, which is a rewriting task with
a source to check against. See `SectionSpec.narrative_register`.

## Why three of these fields are JSON lists rather than child tables

`contraindications`, `special_warnings` and `undesirable_effects` are
lists. They get JSON columns for the same reason `Project.
condition_answers` did (see its comment): they are always read and written
as a whole -- an SmPC section is edited as a unit -- and nothing else in
the dossier points at an individual entry.

What would change our mind, stated so the next person does not have to
guess: the day a side effect has to be linked to the pharmacovigilance
signal or the study that found it, an entry needs an identity, and it
earns its own table.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.product import Product


class ProductInformation(Base):
    """One row per product. The SmPC's authored sections, and nothing else.

    WHY one row and not one per document: see the module docstring. Three
    rows would be three places for the shelf life to be typed.
    """

    __tablename__ = "product_information"

    # Unique: a product has exactly one set of product information, in the
    # same way it has exactly one finished-product specification. The
    # constraint is what makes "the three documents read one row" a
    # database fact rather than a convention the application maintains.
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product.id"), unique=True)
    product: Mapped["Product"] = relationship(back_populates="product_information")

    # ---- SmPC 4. Clinical particulars ---------------------------------
    #
    # One column per numbered SmPC section, named after the section rather
    # than after a shorter English word, so that a reader holding the
    # guideline and a reader holding this file are looking at the same list.

    # 4.1 -- the authorisation itself, in one sentence per indication.
    therapeutic_indications: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 4.2 -- dose, frequency, duration, and HOW it is given. One section in
    # the guideline, so one column: splitting posology from method of
    # administration here would invent a distinction the SmPC does not make.
    posology_and_administration: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 4.3 -- a LIST, not a paragraph. Each entry is one condition under
    # which the product must not be used, because rule R32 has to be able
    # to say which one the leaflet failed to carry over.
    contraindications: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")
    # 4.4 -- special warnings and precautions for use, same shape and the
    # same reason.
    special_warnings: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")
    # 4.5
    interactions: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 4.6 -- fertility, pregnancy and lactation.
    pregnancy_and_lactation: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 4.7
    effects_on_driving: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 4.8 -- a list of `{"effect": ..., "frequency": ...}` entries, where
    # the frequency is an `AdverseEventFrequency` value. Both documents
    # print these grouped by band and in band order, which is only
    # possible because the band is a field and not a heading someone typed.
    undesirable_effects: Mapped[list[dict]] = mapped_column(JSON, default=list, server_default="[]")
    # 4.9
    overdose: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ---- SmPC 6. Pharmaceutical particulars ---------------------------
    #
    # 6.1 (excipients), 6.3 (shelf life), 6.4 (storage) and 6.5 (container)
    # are DELIBERATELY ABSENT: those four are the derived ones, and this is
    # the table where their absence is the design. See the module docstring.
    #
    # 6.2 and 6.6 are here because they exist nowhere else: an
    # incompatibility is a statement about this product in use, and the
    # disposal instruction is a legal requirement of the leaflet.
    incompatibilities: Mapped[str | None] = mapped_column(Text, nullable=True)
    special_precautions_for_disposal: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def contraindication_terms(self) -> list[str]:
        """`contraindications`, defensively coerced to a list of strings.

        WHY this exists rather than reading the column directly: a JSON
        column will hand back whatever was stored, and a row written
        before the schema existed (or by a fixture taking a shortcut) can
        hold None. Every consumer -- two templates, two rules and the
        comparison endpoint -- would otherwise need the same guard, and
        the first one to forget it raises TypeError inside a rendered
        document.
        """
        return [str(entry) for entry in (self.contraindications or [])]

    @property
    def warning_terms(self) -> list[str]:
        return [str(entry) for entry in (self.special_warnings or [])]

    @property
    def adverse_effects(self) -> list[dict]:
        return [entry for entry in (self.undesirable_effects or []) if isinstance(entry, dict)]
