"""Excipient (AGENTS.md §6)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import String, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import CompendialStatus, ExcipientFunction

if TYPE_CHECKING:
    from app.models.product import Product


class Excipient(Base):
    __tablename__ = "excipient"

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product.id"))

    name: Mapped[str] = mapped_column(String(200))
    function: Mapped[ExcipientFunction | None] = mapped_column(
        SAEnum(ExcipientFunction), nullable=True
    )
    grade: Mapped[str | None] = mapped_column(String(40), nullable=True)  # "BP"
    supplier: Mapped[str | None] = mapped_column(String(200), nullable=True)
    compendial_status: Mapped[CompendialStatus | None] = mapped_column(
        SAEnum(CompendialStatus), nullable=True
    )

    product: Mapped["Product"] = relationship(back_populates="excipients")
