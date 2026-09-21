"""Sequence (AGENTS.md §6): one regulatory transaction (`0000`, `0001`...).

Only meaningful for eCTD lifecycle operations (P09), but modeled from the
start so a Project always has at least one Sequence to build toward.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import SequenceStatus, SubmissionUnitType

if TYPE_CHECKING:
    from app.models.correspondence import Correspondence
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

    # P27: where this sequence stands with the agency. Moved through the
    # dedicated status endpoint, which enforces
    # `ALLOWED_SEQUENCE_TRANSITIONS` -- not by PATCHing this column, so a
    # history that could not have happened cannot be recorded.
    status: Mapped[SequenceStatus] = mapped_column(
        SAEnum(SequenceStatus), default=SequenceStatus.DRAFT, server_default="DRAFT"
    )

    # P27: what KIND of transaction this sequence is, in the agency's own
    # vocabulary. Feeds `submission-unit/@type` in the EU regional
    # backbone, which until now was hardcoded to "initial" for every
    # sequence -- so a response to a deficiency letter told the agency it
    # was a fresh submission. See SubmissionUnitType for why this is a
    # different axis from Project.submission_type and
    # Product.registration_type.
    submission_unit_type: Mapped[SubmissionUnitType] = mapped_column(
        SAEnum(SubmissionUnitType),
        default=SubmissionUnitType.INITIAL,
        server_default="INITIAL",
    )

    project: Mapped["Project"] = relationship(back_populates="sequences")
    # P09: the leaf inventory this sequence was built with -- see
    # app/models/sequence_leaf.py for why this is persisted at all.
    leaves: Mapped[list["SequenceLeaf"]] = relationship(
        back_populates="sequence", cascade="all, delete-orphan"
    )
    # P27: letters tied to THIS transaction. Nullable on the other side --
    # plenty of correspondence predates any sequence (see Correspondence).
    correspondence: Mapped[list["Correspondence"]] = relationship(back_populates="sequence")
