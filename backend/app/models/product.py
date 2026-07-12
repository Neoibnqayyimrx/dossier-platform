"""Product: the canonical drug-product record (AGENTS.md §6).

This is master data — it is deliberately NOT owned by a single Project.
The same product can be filed as several Projects over time (a NAFDAC
renewal today, an FDA submission next year); Project.product_id points
here, not the other way round. See build-log.md for why this differs
from the original LAMOX vertical slice, which nested Product 1:1 inside
Project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String, Integer, Numeric, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import DosageForm, LegalStatus, RegistrationType

if TYPE_CHECKING:
    from app.models.active_ingredient import ActiveIngredient
    from app.models.batch_formula import BatchFormulaLine
    from app.models.clinical import ClinicalEntry
    from app.models.excipient import Excipient
    from app.models.manufacturer import Manufacturer
    from app.models.packaging import Packaging
    from app.models.project import Project
    from app.models.stability import StabilityStudy


class Product(Base):
    __tablename__ = "product"

    brand_name: Mapped[str] = mapped_column(String(120))
    generic_name: Mapped[str] = mapped_column(String(200))

    # Strength as value + unit rather than a single "500mg" string, so the
    # rule engine (P06) can compare numbers, not parse text.
    strength_value: Mapped[float | None] = mapped_column(Numeric(10, 3), nullable=True)
    strength_unit: Mapped[str | None] = mapped_column(String(20), nullable=True)  # "mg"

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

    # ---- reverse side of Project -> Product (many Projects per Product) --
    projects: Mapped[list["Project"]] = relationship(back_populates="product")
