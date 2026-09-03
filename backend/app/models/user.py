"""User: the account that authenticates API writes.

Started deliberately minimal (P02) — email + argon2 hash, every
authenticated user could write anywhere. `products` below is the scoping
that comment predicted: Product is the root of ownership (see
Product's WHY), so every user's Projects and their whole data tree are
reached by walking this one relationship.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.product import Product


class User(Base):
    __tablename__ = "user"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    products: Mapped[list["Product"]] = relationship(back_populates="owner")
