"""ValidationOverride: a human's logged decision to export a project
despite one specific rule's unresolved ERROR finding (P06).

WHY this exists as its own row, not a flag on Finding: findings are
recomputed fresh every time `run_all` runs (Finding is a plain dataclass,
never persisted) -- there is nothing to flag. An override is a durable,
project + rule_id-keyed fact ("a human decided R05 doesn't block this
particular project, because...") that outlives any single validation run,
so `Report.is_exportable` can be re-evaluated against it on every
subsequent check without the override having to be re-entered.

WHY `created_by_id` is required, not optional: AGENTS.md §5 requires a
*logged* reason -- an override nobody can attribute to a person is not
an audit trail, just an unexplained bypass.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import String, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.user import User


class ValidationOverride(Base):
    __tablename__ = "validation_override"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id"))
    rule_id: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(Text)
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))

    project: Mapped["Project"] = relationship(back_populates="validation_overrides")
    created_by: Mapped["User"] = relationship()
