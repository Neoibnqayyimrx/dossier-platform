"""Applicant: the legal entity submitting a Project to a regulator (AGENTS.md
§6, Module 1's opening question -- dossier-anatomy.md: "the agency needs to
know *who* is legally responsible").

WHY this didn't exist before P08: nothing before this phase needed to know
who was filing, only what was being filed (Product) and to whom (Project.
region). A NAFDAC cover letter (section 1.0) is *addressed* to the
Director-General but has never actually stated who signs it.

WHY master data (like Manufacturer), not nested 1:1 inside Project: the
same applicant (often a local distributor filing on behalf of a foreign
manufacturer) reasonably files several products/renewals over time --
Project.applicant_id is a many-to-one FK, exactly Product's own precedent.

WHY owner_id here as well as on Product (P15a): Applicant is the second
piece of master data a user creates directly -- it is reached through
/applicants, not through a Product -- so it cannot borrow Product's owner
the way certificates and declarations do. Leaving it unowned would make it
a shared, editable, global table: the same mistake /kb/ingest made.

WHY nullable on Project rather than NOT NULL: a project can exist before
its applicant details are captured (matches shelf_life_months, certificates,
etc. -- "the row can be incomplete" is a P06 completeness concern, R14,
not a schema-level constraint).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.user import User


class Applicant(Base):
    __tablename__ = "applicant"

    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    owner: Mapped["User"] = relationship(back_populates="applicants")

    company_name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)

    contact_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(60), nullable=True)

    # The named signatory on filings made on this applicant's behalf --
    # often a local regulatory affairs representative, not the company's
    # own executive, for a foreign manufacturer filing via a Nigerian agent.
    authorized_representative_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    authorized_representative_title: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # gap Phase 4b: the nine-digit D-U-N-S number FDA's Module 1 backbone
    # carries as the applicant's `id` "with every submission" (Module 1
    # backbone spec v2.6, section III.A.1). On the APPLICANT, not the
    # project: it identifies the legal entity, and FDA wants "the same
    # D-U-N-S number ... for all submissions to an application".
    #
    # Nullable because only FDA asks for it -- rule R34 is what insists on
    # it for an FDA filing. FDA's conformance guide allows 999999999 when a
    # number cannot be obtained before submission; that is the filer's
    # statement to make, so it is entered here and never defaulted.
    duns_number: Mapped[str | None] = mapped_column(String(9), nullable=True)

    projects: Mapped[list["Project"]] = relationship(back_populates="applicant")
