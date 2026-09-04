"""ValidationOverride: a human's logged decision to export a project
despite one specific rule's unresolved ERROR finding (P06).

WHY this exists as its own row, not a flag on Finding: findings are
recomputed fresh every time `run_all` runs (Finding is a plain dataclass,
never persisted) -- there is nothing to flag. An override is a durable,
project + rule_id-keyed fact ("a human decided R05 doesn't block this
particular project, because...") that outlives any single validation run,
so `Report.is_exportable` can be re-evaluated against it on every
subsequent check without the override having to be re-entered.

WHY withdrawal is two nullable columns rather than a DELETE (P15c): an
override that can only be created and never taken back pushes people away
from using it honestly -- the mistaken one stays forever, so the next one
gets logged with a vaguer reason "just in case". Withdrawing is therefore
a new logged fact on the same row: who withdrew it and when. The original
decision, and its reason, remain readable afterwards, which a DELETE
would destroy. Append-only is what makes this an audit trail rather than
a settings toggle.

WHY `created_by_id` is required, not optional: AGENTS.md §5 requires a
*logged* reason -- an override nobody can attribute to a person is not
an audit trail, just an unexplained bypass.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
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

    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    withdrawn_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user.id"), nullable=True)

    @property
    def is_active(self) -> bool:
        """A withdrawn override stops excusing its rule immediately -- the
        engine only ever sees the active ones (see the routers'
        _overridden_rule_ids)."""
        return self.withdrawn_at is None

    project: Mapped["Project"] = relationship(back_populates="validation_overrides")

    # WHY foreign_keys is spelled out (P15c): this table now has TWO FKs to
    # user, so SQLAlchemy can no longer infer which column each
    # relationship joins on and raises AmbiguousForeignKeysError at mapper
    # configuration time -- i.e. on the first query anywhere in the app,
    # not on the line that added the second FK.
    created_by: Mapped["User"] = relationship(foreign_keys=[created_by_id])
    withdrawn_by: Mapped["User | None"] = relationship(foreign_keys=[withdrawn_by_id])
