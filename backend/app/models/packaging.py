"""Packaging (AGENTS.md §6): primary, secondary, artwork, label, leaflet, carton.

P19 gave every row a `role`, because two different CTD sections ask about
packaging and they are not asking about the same material: 3.2.P.7 is the
container closure system of the FINISHED PRODUCT, 3.2.S.6 that of the DRUG
SUBSTANCE. See `PackagingRole` for why this cannot be inferred from
`component`, and `active_ingredient_id` below for the second half of the
same problem.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import String, Text, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import PackagingComponent, PackagingRole

if TYPE_CHECKING:
    from app.models.active_ingredient import ActiveIngredient
    from app.models.product import Product


class Packaging(Base):
    __tablename__ = "packaging"

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product.id"))
    # WHY a drug-substance pack may name its substance, and a drug-product
    # pack never does: 3.2.S.6 is repeated PER DRUG SUBSTANCE (the eCTD DTD
    # repeats `m3-2-s-drug-substance` for the same reason), so a combination
    # product whose two APIs ship in different containers would otherwise
    # file both containers under both substances. Nullable because the
    # common case -- one API, or two shipped identically -- has nothing to
    # disambiguate, and a row with no substance named applies to all of
    # them. Meaningless for a DRUG_PRODUCT row, which is about the finished
    # product as a whole.
    active_ingredient_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("active_ingredient.id"), nullable=True
    )

    role: Mapped[PackagingRole] = mapped_column(
        SAEnum(PackagingRole), default=PackagingRole.DRUG_PRODUCT
    )
    component: Mapped[PackagingComponent] = mapped_column(SAEnum(PackagingComponent))
    description: Mapped[str] = mapped_column(Text)
    material: Mapped[str | None] = mapped_column(String(120), nullable=True)
    artwork_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)

    product: Mapped["Product"] = relationship(back_populates="packaging")
    active_ingredient: Mapped["ActiveIngredient | None"] = relationship()
