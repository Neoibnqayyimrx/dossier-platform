"""ActiveIngredient — the API (active pharmaceutical ingredient), AGENTS.md §6."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import String, Integer, Numeric, Text, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import CompendialStatus

if TYPE_CHECKING:
    from app.models.manufacturer import Manufacturer
    from app.models.product import Product


class ActiveIngredient(Base):
    __tablename__ = "active_ingredient"

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product.id"))
    manufacturer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("manufacturer.id"), nullable=True
    )

    inn_name: Mapped[str] = mapped_column(String(200))  # e.g. "Amoxicillin"
    # Strength as value + unit rather than a single "500mg" string, so the
    # rule engine (P06) can compare numbers, not parse text. Lives here,
    # not on Product, because each active ingredient in a combination
    # product has its own strength (see product.py's docstring).
    strength_value: Mapped[float | None] = mapped_column(Numeric(10, 3), nullable=True)
    strength_unit: Mapped[str | None] = mapped_column(String(20), nullable=True)  # "mg"
    salt_form: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # WHY salt_factor: the API you WEIGH (e.g. trihydrate) is heavier than the
    # base the label CLAIMS. Storing the factor lets the validator reconcile
    # a declared batch quantity deterministically (see rule R04).
    salt_factor: Mapped[float] = mapped_column(Numeric(6, 4), default=1.0)
    compendial_std: Mapped[CompendialStatus | None] = mapped_column(
        SAEnum(CompendialStatus), nullable=True
    )

    dmf_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    cep_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    retest_period_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    specifications: Mapped[str | None] = mapped_column(Text, nullable=True)
    particle_size: Mapped[str | None] = mapped_column(String(120), nullable=True)
    residual_solvents: Mapped[str | None] = mapped_column(Text, nullable=True)
    # SMILES string for the API's structural formula -- public chemistry,
    # never copyrighted text. Lets the template engine (P04) render a real
    # 2D structure image (via RDKit) into e.g. the QOS section, instead of
    # a scanned image or a hand-drawn one.
    smiles: Mapped[str | None] = mapped_column(String(500), nullable=True)

    product: Mapped["Product"] = relationship(back_populates="apis")
    manufacturer: Mapped["Manufacturer | None"] = relationship(back_populates="apis")
