"""ClinicalEntry (AGENTS.md §6): bioequivalence, literature, or a clinical study."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import String, Text, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import ClinicalKind

if TYPE_CHECKING:
    from app.models.product import Product


class ClinicalEntry(Base):
    __tablename__ = "clinical_entry"

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product.id"))

    kind: Mapped[ClinicalKind] = mapped_column(SAEnum(ClinicalKind))
    reference_product: Mapped[str | None] = mapped_column(String(200), nullable=True)
    summary: Mapped[str] = mapped_column(Text)

    product: Mapped["Product"] = relationship(back_populates="clinical")
