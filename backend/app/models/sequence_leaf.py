"""SequenceLeaf (P09): a durable record of one leaf as it appeared in one
built eCTD sequence.

WHY this exists as its own table, not recomputed on the fly: the lifecycle
resolver (`app.ectd.lifecycle`) needs to know what the *prior* sequence
actually contained the next time someone builds a new one -- possibly a
separate API call, possibly days later. `Sequence` itself (P01) is just a
bare marker (number/description/submitted_at); it never recorded what was
inside a build. Without this table, "did this leaf change since last time"
would have nothing to compare against once the in-memory build finishes.

`section_key` is the STABLE identity of a logical document across sequences
(a `SECTIONS` number like "3.2.P.1", or a Module1Slot's `slot_id` like
"cover-letter") -- it never changes between sequences even though `leaf_id`
does (see `app.ectd.leaf`'s WHY comment for the ID scheme). The lifecycle
resolver joins old-vs-new leaf sets on `section_key`, never on `leaf_id`.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.sequence import Sequence


class SequenceLeaf(Base):
    __tablename__ = "sequence_leaf"

    sequence_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sequence.id"))

    section_key: Mapped[str] = mapped_column(String(100))
    leaf_id: Mapped[str] = mapped_column(String(100))  # the eCTD `ID` attribute used
    title: Mapped[str] = mapped_column(String(300))
    path: Mapped[str] = mapped_column(String(500))  # xlink:href, relative to sequence root
    checksum: Mapped[str] = mapped_column(String(32))  # MD5 hex digest

    operation: Mapped[str] = mapped_column(String(10))  # new | replace | append | delete
    # relative-path-into-a-prior-sequence + that leaf's ID, e.g.
    # "../0000/m3/.../3.2.P.1.pdf#ID_32P1_0000" -- None for `operation="new"`.
    modified_file: Mapped[str | None] = mapped_column(String(600), nullable=True)

    sequence: Mapped["Sequence"] = relationship(back_populates="leaves")
