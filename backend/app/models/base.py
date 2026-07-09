"""Declarative base: every table gets a UUID primary key and timestamps.

WHY a shared Base: keeps id/created_at/updated_at identical everywhere, so the
rest of the model files stay focused on domain fields only. The `Uuid` type
maps to a native UUID on Postgres and to CHAR(32) on SQLite, so this same code
runs in the real stack (Postgres) and in this runnable slice (SQLite).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Uuid, DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
