"""Correspondence: the letters between the applicant and the agency (P27).

WHY this is worth a table when the platform does not yet have a UI for it:
a registration is not a package, it is a CONVERSATION. The dossier goes in
and what comes back is a deficiency letter with a deadline; the answer to
that letter is itself a sequence; the commitment made in the answer has to
be honoured months later. Until now none of that existed anywhere in the
schema, so the platform could produce a perfect submission and had no way
to represent the reply that decided whether it was approved.

The thing that makes it urgent rather than merely nice is the CLOCK. A
deficiency letter carries a response deadline, and missing it can lapse the
application -- the dossier is fine and the registration is lost on a date.
`due_date` plus `status` is the smallest honest model of that: what is
outstanding, and by when.

WHY it hangs off Project with a NULLABLE sequence:

  - Project, because the conversation is about this filing, and because
    project ownership is the authorization boundary every other route
    already uses.
  - sequence_id nullable, because a great deal of real correspondence has
    no sequence to point at. A pre-submission meeting request, a general
    query about a guideline, an agency notice about fees -- all belong to
    the application and none belong to a transaction. Forcing a sequence
    would mean inventing one, and an invented sequence number is a
    regulatory identifier that does not exist.

WHY there is no `body` column: the letter itself is a document, and
documents already have a home. `section_document_id` points at the file
when one has been uploaded. Retyping a regulator's letter into a text
column would create a second version of it that nobody could check against
the original.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import (
    CorrespondenceDirection,
    CorrespondenceStatus,
    CorrespondenceType,
)

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.section_document import SectionDocument
    from app.models.sequence import Sequence


class Correspondence(Base):
    __tablename__ = "correspondence"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id"))

    # Nullable on purpose -- see the module docstring. ON DELETE SET NULL
    # rather than CASCADE: deleting a sequence must not silently destroy
    # the record of the agency's letter about it. The letter outlives the
    # transaction it referred to.
    sequence_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sequence.id", ondelete="SET NULL"), nullable=True
    )

    direction: Mapped[CorrespondenceDirection] = mapped_column(SAEnum(CorrespondenceDirection))
    correspondence_type: Mapped[CorrespondenceType] = mapped_column(SAEnum(CorrespondenceType))

    subject: Mapped[str] = mapped_column(String(300))

    # One column for both directions rather than separate sent_at/received_at:
    # every item has exactly one of those, `direction` already says which,
    # and two nullable columns would allow the meaningless state where both
    # or neither is set.
    received_or_sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # A Date, not a DateTime: an agency gives a deadline of "by 14 March",
    # never "by 14 March at 16:20". Storing a time would invent a precision
    # the obligation does not have, and then someone would compare against
    # it.
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    status: Mapped[CorrespondenceStatus] = mapped_column(
        SAEnum(CorrespondenceStatus),
        default=CorrespondenceStatus.OPEN,
        server_default="OPEN",
    )

    # Free text for the filer's own context -- "answered in 0002", "agreed
    # by phone with the assessor". Explicitly NOT the letter's contents;
    # see the module docstring on why the letter stays a document.
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # The uploaded letter, when there is one. SET NULL for the same reason
    # as sequence_id: losing the file should not erase the fact that the
    # letter existed and what it demanded.
    section_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("section_document.id", ondelete="SET NULL"), nullable=True
    )

    project: Mapped["Project"] = relationship(back_populates="correspondence")
    sequence: Mapped["Sequence | None"] = relationship(back_populates="correspondence")
    document: Mapped["SectionDocument | None"] = relationship()

    @property
    def is_overdue(self) -> bool:
        """Open, dated, and the date has passed.

        A CLOSED item is never overdue however old its due date: the work
        was done. Reading "overdue" off the due date alone would light up
        every historical letter the platform has ever recorded.
        """
        if self.status is not CorrespondenceStatus.OPEN or self.due_date is None:
            return False
        return self.due_date < date.today()
