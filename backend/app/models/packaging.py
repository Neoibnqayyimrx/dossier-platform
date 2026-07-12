"""Packaging (AGENTS.md §6): primary, secondary, artwork, label, leaflet, carton."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import String, Text, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import PackagingComponent

if TYPE_CHECKING:
    from app.models.product import Product


class Packaging(Base):
    __tablename__ = "packaging"

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product.id"))

    component: Mapped[PackagingComponent] = mapped_column(SAEnum(PackagingComponent))
    description: Mapped[str] = mapped_column(Text)
    material: Mapped[str | None] = mapped_column(String(120), nullable=True)
    artwork_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)

    product: Mapped["Product"] = relationship(back_populates="packaging")
