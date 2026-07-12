"""Sequence (AGENTS.md §6): one regulatory transaction (`0000`, `0001`...).

Only meaningful for eCTD lifecycle operations (P09), but modeled from the
start so a Project always has at least one Sequence to build toward.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.project import Project


class Sequence(Base):
    __tablename__ = "sequence"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id"))

    number: Mapped[str] = mapped_column(String(4))  # "0000", "0001", ...
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="sequences")
