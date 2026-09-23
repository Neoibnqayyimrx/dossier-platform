"""Organization: the tenant (gap Phase 6a).

Until this phase the unit of access was one USER: a Product belonged to
whoever created it, and nobody else could ever see it. A regulatory affairs
department is several people working one dossier -- the lead, the CMC
writer, the reviewer -- so per-user ownership made the platform a single-
seat tool. The Organization is the unit of access now: every Product and
Applicant belongs to one, every User is a member of one, and a user reaches
exactly what their organization holds.

Decisions the user made for this phase (recorded in docs/decisions/0004):

- ONE organization per user (`User.organization_id`), not a membership
  table. A consultant serving two companies holds two accounts.
- Existing data migrated to one organization PER EXISTING USER, so nobody
  can see anything after the migration that they could not see before.
- A platform SUPER-ADMIN exists, for accounts only: it creates
  organizations and manages accounts across them, and it reads no
  organization's dossiers -- the same "administration is not a data
  bypass" line the global ADMIN has always held.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.applicant import Applicant
    from app.models.product import Product
    from app.models.user import User


class Organization(Base):
    __tablename__ = "organization"

    name: Mapped[str] = mapped_column(String(200))

    users: Mapped[list["User"]] = relationship(back_populates="organization")
    products: Mapped[list["Product"]] = relationship(back_populates="organization")
    applicants: Mapped[list["Applicant"]] = relationship(back_populates="organization")
