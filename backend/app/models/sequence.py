"""Sequence (AGENTS.md §6): one regulatory transaction (`0000`, `0001`...).

Only meaningful for eCTD lifecycle operations (P09), but modeled from the
start so a Project always has at least one Sequence to build toward.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.sequence_leaf import SequenceLeaf


class Sequence(Base):
    __tablename__ = "sequence"

    # WHY a database constraint and not just care in the endpoint: the
    # sequence number is a REGULATORY identifier. Every eCTD transaction to
    # an agency is filed under it, and a lifecycle operation in sequence
    # 0003 points back at a leaf in 0002 by that number. Two rows sharing a
    # number is not a display bug -- it is a corrupt submission history that
    # no later code can unambiguously repair, because nothing records which
    # of the two was "really" 0003. Application-level checks cannot prevent
    # it: two concurrent POSTs can both read max()=0002 before either
    # inserts. Only the database can refuse the second write, so the
    # constraint is the guarantee and the retry in create_sequence is merely
    # the recovery.
    __table_args__ = (UniqueConstraint("project_id", "number", name="uq_sequence_project_number"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id"))

    number: Mapped[str] = mapped_column(String(4))  # "0000", "0001", ...
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="sequences")
    # P09: the leaf inventory this sequence was built with -- see
    # app/models/sequence_leaf.py for why this is persisted at all.
    leaves: Mapped[list["SequenceLeaf"]] = relationship(
        back_populates="sequence", cascade="all, delete-orphan"
    )
