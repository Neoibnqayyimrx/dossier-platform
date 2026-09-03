"""Product: the canonical drug-product record (AGENTS.md §6).

This is master data — it is deliberately NOT owned by a single Project.
The same product can be filed as several Projects over time (a NAFDAC
renewal today, an FDA submission next year); Project.product_id points
here, not the other way round. See build-log.md for why this differs
from the original LAMOX vertical slice, which nested Product 1:1 inside
Project.

WHY owner_id lives here and not on Project: Product is the root of
everything a user can touch — every Project points at a Product, and
every child resource (manufacturers, excipients, specs, ...) hangs off
Product or off an ActiveIngredient that itself hangs off Product. One
owner column here, checked once, covers the whole tree instead of a
column (and a check) repeated on every table.

WHY strength is NOT a column here (it moved to ActiveIngredient): a
fixed-dose combination product -- Ampiclox (ampicillin + cloxacillin),
artemether-lumefantrine -- doesn't have ONE strength, it has one per
active ingredient. A single `strength_value`/`strength_unit` pair on
Product had no honest place to put a second value, which silently made
every combination product unrepresentable. `strength_display` below
derives a human-readable joined string from whatever APIs actually exist,
so single- and multi-API products render the same way without a
special case.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Integer, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import DosageForm, LegalStatus, RegistrationType

if TYPE_CHECKING:
    from app.models.active_ingredient import ActiveIngredient
    from app.models.batch_formula import BatchFormulaLine
    from app.models.certificate import Certificate
    from app.models.clinical import ClinicalEntry
    from app.models.excipient import Excipient
    from app.models.manufacturer import Manufacturer
    from app.models.packaging import Packaging
    from app.models.project import Project
    from app.models.stability import StabilityStudy
    from app.models.user import User


class Product(Base):
    __tablename__ = "product"

    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    owner: Mapped["User"] = relationship(back_populates="products")

    brand_name: Mapped[str] = mapped_column(String(120))
    generic_name: Mapped[str] = mapped_column(String(200))

    dosage_form: Mapped[DosageForm | None] = mapped_column(SAEnum(DosageForm), nullable=True)
    atc_code: Mapped[str | None] = mapped_column(String(20), nullable=True)

    shelf_life_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_condition: Mapped[str | None] = mapped_column(String(300), nullable=True)
    pack_size: Mapped[str | None] = mapped_column(String(120), nullable=True)  # "10x10 blister"
    route_of_administration: Mapped[str | None] = mapped_column(String(60), nullable=True)

    legal_status: Mapped[LegalStatus | None] = mapped_column(SAEnum(LegalStatus), nullable=True)
    registration_type: Mapped[RegistrationType | None] = mapped_column(
        SAEnum(RegistrationType), nullable=True
    )
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)

    # ---- children (Product has many of each — AGENTS.md §6) --------------
    manufacturers: Mapped[list["Manufacturer"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    apis: Mapped[list["ActiveIngredient"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    excipients: Mapped[list["Excipient"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    packaging: Mapped[list["Packaging"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    stability: Mapped[list["StabilityStudy"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    clinical: Mapped[list["ClinicalEntry"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    batch_formula: Mapped[list["BatchFormulaLine"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    certificates: Mapped[list["Certificate"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )

    # ---- reverse side of Project -> Product (many Projects per Product) --
    projects: Mapped[list["Project"]] = relationship(back_populates="product")

    @property
    def strength_display(self) -> str:
        """Human-readable strength(s), one "name value unit" per active
        ingredient that has a strength on file, joined with " + " for
        combination products (e.g. "Ampicillin 250 mg + Cloxacillin 250
        mg"). A single-API product just renders as one term -- there is no
        special case for "one active" vs "several"."""
        parts = []
        for api in self.apis:
            if api.strength_value is None:
                continue
            value = f"{float(api.strength_value):g}"
            unit = api.strength_unit or ""
            parts.append(f"{api.inn_name} {value} {unit}".strip())
        return " + ".join(parts)
