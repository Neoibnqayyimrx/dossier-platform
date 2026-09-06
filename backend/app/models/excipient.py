"""Excipient (AGENTS.md §6)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import String, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import CompendialStatus, ExcipientFunction, ExcipientOrigin

if TYPE_CHECKING:
    from app.models.product import Product
    from app.models.specification import SpecificationTest


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
    # P19: what the material is made from, which is what 3.2.P.4.5 asks and
    # rule R21 checks. Nullable, and nullable MEANS SOMETHING here: "not
    # stated" is not "synthetic". See ExcipientOrigin's docstring -- an
    # excipient's name does not reveal its origin, so this is one of the
    # few facts in Module 3 that only the filer can supply.
    origin: Mapped[ExcipientOrigin | None] = mapped_column(SAEnum(ExcipientOrigin), nullable=True)

    product: Mapped["Product"] = relationship(back_populates="excipients")
    # P20: 3.2.P.4.1 -- the excipient's own specification, repeated per
    # excipient. The SAME table the drug substance's 3.2.S.4.1 renders
    # from; see app/models/spec_owner.py for why that is one table and not
    # three near-identical ones.
    specification: Mapped[list["SpecificationTest"]] = relationship(
        back_populates="excipient",
        cascade="all, delete-orphan",
        order_by="SpecificationTest.sort_order",
    )
