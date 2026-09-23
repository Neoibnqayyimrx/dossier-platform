"""User: the account that authenticates API writes.

Started deliberately minimal (P02) — email + argon2 hash, every
authenticated user could write anywhere. `products` below is the scoping
that comment predicted: Product is the root of ownership (see
Product's WHY), so every user's Projects and their whole data tree are
reached by walking this one relationship.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import uuid

from sqlalchemy import Boolean, Enum as SAEnum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import UserRole

if TYPE_CHECKING:
    from app.models.applicant import Applicant
    from app.models.organization import Organization
    from app.models.product import Product


class User(Base):
    __tablename__ = "user"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # gap Phase 6a: the role is now WITHIN the user's organization -- an
    # ADMIN manages its members (app.api.routers.admin), a USER works its
    # dossiers. Access to data is decided by `organization_id`, never by
    # role: an admin reads nothing a user of the same organization cannot.
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole), default=UserRole.USER)

    # gap Phase 6a: the organization this account belongs to -- ONE per
    # user, by the user's decision (see app/models/organization.py).
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organization.id"))
    # lazy="joined": every UserRead nests the organization, and a lazy load
    # on the async engine raises MissingGreenlet (see app/api/loading.py).
    # One many-to-one row joined onto a user lookup costs nothing, and it
    # means no endpoint that returns a user can forget to load it.
    organization: Mapped["Organization"] = relationship(back_populates="users", lazy="joined")

    # gap Phase 6a: platform account administration ACROSS organizations
    # (app.api.routers.superadmin). Deliberately NOT a data bypass: every
    # ownership check compares organizations, and this flag appears in none
    # of them. A separate flag rather than a third UserRole, because it is
    # orthogonal: a super-admin is also a member of their own organization,
    # with a role in it like anyone else.
    is_superadmin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

    # Since gap Phase 6a these record who CREATED an item, not who may reach
    # it -- that is the organization's (see Product.organization_id).
    products: Mapped[list["Product"]] = relationship(back_populates="owner")
    # The second owned root (P15a): an Applicant is created directly, not
    # through a Product, so it carries its own owner (see its WHY).
    applicants: Mapped[list["Applicant"]] = relationship(back_populates="owner")
