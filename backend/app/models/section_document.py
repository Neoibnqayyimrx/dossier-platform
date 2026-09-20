"""SectionDocument: a real file a human attached to a leaf of the dossier
(P18).

WHY this is the phase that changes what the platform IS: roughly a quarter
of a real dossier consists of artifacts nobody here can author -- a
regulator's Certificate of Pharmaceutical Product, a contract lab's method
validation report, a CRO's bioequivalence study report. Until now the build
emitted a clearly-marked placeholder in each of those slots, which made the
package structurally perfect and not submittable. This table is where the
actual paper goes.

WHY it is keyed by SECTION INSTANCE (number + subject slug) rather than by
section number: `app/templating/instances.py` already made this argument for
rendered documents, and it applies with more force to uploaded ones.
"3.2.S.3.1" does not name one document once a product has two active
ingredients -- an elucidation-of-structure report is about ampicillin OR
cloxacillin, never both, and filing one under a number that means "both"
would put the wrong substance's spectra in front of an assessor.

WHY it hangs off Project and not Product, even though a GMP certificate is
arguably a fact about a site rather than a filing: the leaf number it
answers is a fact about THIS submission's table of contents, and the same
certificate can legitimately sit at different numbers in different regions'
Module 1. Scoping to the project also makes the storage prefix
(`projects/{project_id}/`) the authorization boundary, which is the check
`app/api/routers/artifacts.py` already relies on and documents.

P26 UPDATE -- this row is now the CURRENT VERSION of the leaf, and every
upload that has ever stood here is kept in `document_version`. The P18 note
this paragraph used to carry said replacing an upload overwrote it and that
the sequence-level history was enough; it was not, because between two
sequences a leaf can be replaced any number of times and each replacement
destroyed its predecessor irrecoverably. See `app/models/document_version.py`.

WHY the file columns below still live here rather than being read through
the current version row: every consumer -- `app/assembly/assemble.py`, the
lifecycle resolver, the validation rules -- already reads `storage_key` and
`md5` off this object, and none of them should have to learn about
versioning to keep working. The columns are a deliberate denormalisation of
the newest `document_version` row, with the invariant "these columns equal
this document's highest-numbered version" asserted by a test. See
docs/decisions/0003-document-versioning.md.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.document_version import DocumentVersion
    from app.models.project import Project
    from app.models.user import User


class SectionDocument(Base):
    __tablename__ = "section_document"
    __table_args__ = (
        # One document per leaf. WHY a database constraint rather than a
        # check in the endpoint: two leaves at the same number would produce
        # two files at the same path in the package, and a zip with a
        # duplicate entry is a corrupt submission. The upload endpoint
        # replaces in place precisely so this can never be reached, and the
        # constraint is what makes that guarantee structural.
        UniqueConstraint(
            "project_id",
            "section_number",
            "subject_slug",
            name="uq_section_document_leaf",
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id"))

    # The leaf this file answers, e.g. "1.2.7" or "3.2.S.3.1".
    section_number: Mapped[str] = mapped_column(String(20))
    # Which drug substance this copy is about, for sections repeated per
    # substance; empty string (never NULL) for a once-per-project leaf.
    #
    # WHY "" and not NULL: in SQL, NULL != NULL, so a UNIQUE constraint over
    # a nullable column does not actually prevent two rows with a NULL
    # subject -- the duplicate-leaf bug the constraint above exists to stop
    # would sail straight through for exactly the common case. An empty
    # string compares equal to itself.
    subject_slug: Mapped[str] = mapped_column(String(120), default="")

    # Where the SHIPPING bytes live -- see app/documents/ingest.py: a
    # non-PDF upload is converted at upload time, so this key always points
    # at the PDF that will actually go in the package.
    storage_key: Mapped[str] = mapped_column(String(500))
    # MD5 of those same shipping bytes. Stored, not recomputed at build
    # time, because it is the value the eCTD manifest and index.xml publish
    # -- and a checksum that can be recomputed differently later is not a
    # checksum.
    md5: Mapped[str] = mapped_column(String(32))
    size_bytes: Mapped[int] = mapped_column(Integer)

    # What the human uploaded, kept for display: "CPP_NAFDAC_2026.pdf" is
    # how they will recognise it, and "1.2.7.pdf" is not.
    original_filename: Mapped[str] = mapped_column(String(300))
    content_type: Mapped[str] = mapped_column(String(120))

    # WHY the uploader is recorded and the row is not deleted when they are:
    # "who attached the CPP we filed" is an audit question, and an
    # attachment whose provenance evaporates when someone leaves the company
    # is worth less than one that does not.
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    project: Mapped["Project"] = relationship(back_populates="documents")
    uploaded_by: Mapped["User | None"] = relationship()

    # Newest last, so `versions[-1]` is the current one and the history
    # reads in the order it happened.
    versions: Mapped[list["DocumentVersion"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentVersion.version_number",
    )

    @property
    def instance_key(self) -> str:
        """The identity `app/templating/instances.py` uses for a rendered
        document, so an uploaded leaf and a rendered one are addressable the
        same way: "3.2.P.1", or "3.2.S.1-ampicillin"."""
        if not self.subject_slug:
            return self.section_number
        return f"{self.section_number}-{self.subject_slug}"
