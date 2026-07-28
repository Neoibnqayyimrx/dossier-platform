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

WHY nullable on Project rather than NOT NULL: a project can exist before
its applicant details are captured (matches shelf_life_months, certificates,
etc. -- "the row can be incomplete" is a P06 completeness concern, R14,
not a schema-level constraint).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.project import Project


class Applicant(Base):
    __tablename__ = "applicant"

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

    projects: Mapped[list["Project"]] = relationship(back_populates="applicant")
