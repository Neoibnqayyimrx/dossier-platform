"""BatchFormulaLine: one row of the 3.2.P.1 composition table.

Not one of AGENTS.md §6's canonical entities on its own — it's the structured
backing for Product's composition table, and what rules R01/R02/R04 (P06)
and the template engine (P04) actually read. Per-unit quantity plus batch
size lets the batch quantity be reconstructed, and checked, deterministically.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import String, Integer, Numeric, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.product import Product


class BatchFormulaLine(Base):
    __tablename__ = "batch_formula_line"
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product.id"))

    component: Mapped[str] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(default=False)
    spec: Mapped[str] = mapped_column(String(40))  # "BP"
    qty_per_unit_mg: Mapped[float] = mapped_column(Numeric(12, 4))
    batch_size_units: Mapped[int] = mapped_column(Integer)  # 250000
    declared_batch_qty_kg: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)

    product: Mapped["Product"] = relationship(back_populates="batch_formula")
