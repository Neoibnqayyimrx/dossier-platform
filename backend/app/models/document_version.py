"""DocumentVersion: every file that has ever stood at a leaf (P26).

P18 shipped uploads with a deliberate simplification, recorded as one in
`section_document.py`: replacing an upload overwrote it, in the row and in
object storage alike. The argument for accepting that was that eCTD
lifecycle already versions at the SEQUENCE level, so the history a
regulator sees was preserved even though the working copy's was not.

WHY that is no longer enough. The sequence-level history only covers what
was FILED. It cannot answer the questions an audit actually asks about the
period before a filing:

  - "Which CPP did we attach in March, and who replaced it in April?"
  - "The assessor's copy of 3.2.S.3.1 differs from ours -- when did it
    change, and to what?"
  - "We filed sequence 0000 with this bioequivalence report. Show me the
    one it replaced."

Between two sequences a leaf can be replaced any number of times and, under
P18, each replacement destroyed its predecessor's bytes irrecoverably. A
dossier is a regulated record; "we overwrote it" is not an answer.

WHY a separate table rather than an `is_current` flag on `section_document`
(see docs/decisions/0003-document-versioning.md for the full argument): the
whole build path -- `app/assembly/assemble.py`, the lifecycle resolver, the
validation rules -- reads `document.storage_key` and `document.md5` off
SectionDocument today. Keeping SectionDocument as the current-version row
means none of them changes, and the unique constraint that stops two files
landing at one leaf keeps working unconditionally rather than becoming a
partial index over `is_current`.

WHY each version gets its OWN storage key: under P18 every upload for a
leaf wrote to the same deterministic key, so the new bytes replaced the old
ones in the bucket. Version rows pointing at a key that no longer holds
their bytes would be a history that lies, which is worse than no history.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.section_document import SectionDocument
    from app.models.user import User


class DocumentVersion(Base):
    __tablename__ = "document_version"
    __table_args__ = (
        # WHY the database enforces this and not just the endpoint: the
        # version number is how a version is ADDRESSED -- the history
        # endpoint and the bytes endpoint both take it -- so two rows
        # sharing one is an ambiguous URL, and "version 2" would mean
        # different bytes depending on row order. Exactly the reasoning
        # behind the sequence-number constraint added in gap Phase 1, and
        # the upload path handles a collision the same way: retry, because
        # read-max-then-insert is not atomic.
        UniqueConstraint(
            "section_document_id",
            "version_number",
            name="uq_document_version_number",
        ),
    )

    # WHY the FK hangs off SectionDocument rather than repeating
    # (project_id, section_number, subject_slug): SectionDocument already
    # owns that identity and enforces its uniqueness. Repeating the triple
    # here would let a version drift to a different leaf than its parent,
    # which no constraint could then catch.
    section_document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("section_document.id", ondelete="CASCADE")
    )

    # 1 for the first upload at this leaf, then 2, 3... Never reused, even
    # if a version is deleted: it names a historical fact.
    version_number: Mapped[int] = mapped_column(Integer)

    # This version's OWN bytes. Distinct per version -- see the module
    # docstring on why sharing one key would make the history a lie.
    storage_key: Mapped[str] = mapped_column(String(500))
    md5: Mapped[str] = mapped_column(String(32))
    size_bytes: Mapped[int] = mapped_column(Integer)

    original_filename: Mapped[str] = mapped_column(String(300))
    content_type: Mapped[str] = mapped_column(String(120))

    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    document: Mapped["SectionDocument"] = relationship(back_populates="versions")
    uploaded_by: Mapped["User | None"] = relationship()
