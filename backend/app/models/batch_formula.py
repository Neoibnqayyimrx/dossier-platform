"""BatchFormulaLine: one row of the 3.2.P.1 composition table.

Not one of AGENTS.md §6's canonical entities on its own — it's the structured
backing for Product's composition table, and what rules R01/R02/R04 (P06)
and the template engine (P04) actually read. Per-unit quantity plus batch
size lets the batch quantity be reconstructed, and checked, deterministically.

WHY active_ingredient_id: for a combination product (2+ actives, each with
its own salt_factor), a rule reconciling batch quantity against strength
needs to know WHICH active ingredient a given active line represents --
`is_active=True` alone doesn't disambiguate which active. Nullable because
excipient lines have no associated API at all.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import String, Integer, Numeric, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.active_ingredient import ActiveIngredient
    from app.models.product import Product


class BatchFormulaLine(Base):
    __tablename__ = "batch_formula_line"
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product.id"))
    active_ingredient_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("active_ingredient.id"), nullable=True
    )

    component: Mapped[str] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(default=False)
    spec: Mapped[str] = mapped_column(String(40))  # "BP"
    qty_per_unit_mg: Mapped[float] = mapped_column(Numeric(12, 4))
    batch_size_units: Mapped[int] = mapped_column(Integer)  # 250000
    declared_batch_qty_kg: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)

    product: Mapped["Product"] = relationship(back_populates="batch_formula")
    active_ingredient: Mapped["ActiveIngredient | None"] = relationship()
