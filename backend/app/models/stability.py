"""StabilityStudy (AGENTS.md §6).

Each study is one row: type (accelerated/long-term/intermediate), condition,
duration, and a results summary. Modeling type + duration as separate typed
fields — instead of folding them into prose — is what lets the validation
engine (P06) compare a product's declared shelf life against the *longest
long-term study duration on file*, rather than parsing a sentence.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import String, Integer, Text, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import StabilityStudyType

if TYPE_CHECKING:
    from app.models.product import Product


class StabilityStudy(Base):
    __tablename__ = "stability_study"

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product.id"))

    study_type: Mapped[StabilityStudyType] = mapped_column(SAEnum(StabilityStudyType))
    condition: Mapped[str] = mapped_column(String(80))  # "30C/65%RH"
    duration_months: Mapped[int] = mapped_column(Integer)
    protocol: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_summary: Mapped[str] = mapped_column(Text)

    product: Mapped["Product"] = relationship(back_populates="stability")
