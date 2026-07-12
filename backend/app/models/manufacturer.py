"""Manufacturer (AGENTS.md §6).

A Product can list several manufacturers playing different roles — the
finished-product site is frequently not the same site that makes the API.
`ActiveIngredient.manufacturer_id` points at whichever row here plays the
API_MANUFACTURER role for that product.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import String, Boolean, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import GMPStatus, ManufacturerRole

if TYPE_CHECKING:
    from app.models.active_ingredient import ActiveIngredient
    from app.models.product import Product


class Manufacturer(Base):
    __tablename__ = "manufacturer"

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product.id"))

    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[ManufacturerRole] = mapped_column(SAEnum(ManufacturerRole))
    site_address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)

    gmp_status: Mapped[GMPStatus | None] = mapped_column(SAEnum(GMPStatus), nullable=True)
    who_gmp: Mapped[bool] = mapped_column(Boolean, default=False)
    pic_s: Mapped[bool] = mapped_column(Boolean, default=False)
    manufacturing_licence: Mapped[str | None] = mapped_column(String(120), nullable=True)

    product: Mapped["Product"] = relationship(back_populates="manufacturers")
    apis: Mapped[list["ActiveIngredient"]] = relationship(back_populates="manufacturer")
