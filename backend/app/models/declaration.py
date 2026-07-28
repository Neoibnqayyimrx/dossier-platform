"""Declaration: a Module 1 administrative document whose text we CAN
generate (Power of Attorney, Declaration of Authenticity, GMP Compliance
Undertaking) but which is only real once a human signs it -- and, for
some types, has it notarized/legalized (dossier-anatomy.md's "notarized/
legalized declarations").

WHY this is a distinct model from Certificate, not another CertificateType:
a Certificate's content is unknown to us -- a regulator or lab issues it,
we only record metadata about a document we don't have. A Declaration's
content is fully known (it's built from Applicant/Product/Project data,
same as the cover letter) -- what's missing isn't the content, it's a wet
signature and a notary's seal. That's a different placeholder message
("SIGN AND NOTARIZE", not "REPLACE THIS FILE") and a different completeness
check (R15 checks `signed`/`notarized` flags, not "does a row exist").

WHY project-scoped, not product-scoped (unlike Certificate): a Power of
Attorney names a representative for THIS specific filing -- the same
product filed as a later renewal could use a different declaration.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import DeclarationType

if TYPE_CHECKING:
    from app.models.project import Project


class Declaration(Base):
    __tablename__ = "declaration"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id"))
    declaration_type: Mapped[DeclarationType] = mapped_column(SAEnum(DeclarationType))

    signed: Mapped[bool] = mapped_column(Boolean, default=False)
    signed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notarized: Mapped[bool] = mapped_column(Boolean, default=False)
    notarization_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    project: Mapped["Project"] = relationship(back_populates="declarations")
