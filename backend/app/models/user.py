"""User (P02): the account that authenticates API writes.

Deliberately minimal — email + argon2 hash. No roles/permissions yet; every
authenticated user can write. Add scoping later if the wizard (P11) needs it.
"""

from __future__ import annotations

from sqlalchemy import String, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class User(Base):
    __tablename__ = "user"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
