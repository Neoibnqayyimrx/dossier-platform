"""gap Phase 6a: organizations -- the tenant above users, products, applicants

Adds `organization`, and `organization_id` on user, product and applicant;
adds `user.is_superadmin`.

DATA MIGRATION -- the user's decision, and the reason it is safe:

  * ONE ORGANIZATION PER EXISTING USER, named after their email, holding
    exactly the products and applicants that user owned. Access moves from
    "the owner" to "the owner's organization", and with one member per
    organization those are the same people: nobody can see anything after
    this migration that they could not see before it.
  * Every existing user becomes the ADMIN of their own organization -- they
    hold everything in it, and someone must be able to add colleagues.
  * Every existing GLOBAL admin becomes a platform super-admin
    (`is_superadmin`), which is what the old global role meant: account
    administration across everyone, never a data bypass.

Downgrade restores the old roles exactly, because the upgrade's mapping is
reversible: a user was a global ADMIN if and only if they are now a
super-admin.

Revision ID: c5b8e2d4f071
Revises: a7d4c1f09e62
Create Date: 2026-09-22
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "c5b8e2d4f071"
down_revision = "a7d4c1f09e62"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organization",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # Nullable first: the backfill below fills them, THEN they tighten.
    with op.batch_alter_table("user") as batch_op:
        batch_op.add_column(sa.Column("organization_id", sa.Uuid(), nullable=True))
        batch_op.add_column(
            sa.Column("is_superadmin", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    for table in ("product", "applicant"):
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(sa.Column("organization_id", sa.Uuid(), nullable=True))

    bind = op.get_bind()
    # Table stubs as of THIS revision, not the live models -- a migration is
    # a record of the schema at a point in time (see the P27 migration).
    organization = sa.table(
        "organization",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    user = sa.table(
        "user",
        # UNTYPED on purpose: the id is only ever read and then compared back,
        # so it must round-trip exactly as stored. Typed as Uuid, SQLite would
        # compare a 32-hex bind against a row inserted as a hyphenated string
        # and match nothing -- found writing this migration's own test.
        sa.column("id"),
        sa.column("email", sa.String()),
        sa.column("role", sa.String()),
        sa.column("organization_id", sa.Uuid()),
        sa.column("is_superadmin", sa.Boolean()),
    )
    now = datetime.now(timezone.utc)
    for user_id, email, role in bind.execute(sa.select(user.c.id, user.c.email, user.c.role)):
        org_id = uuid.uuid4()
        bind.execute(
            organization.insert().values(
                id=org_id, name=f"{email}'s organization", created_at=now, updated_at=now
            )
        )
        bind.execute(
            user.update()
            .where(user.c.id == user_id)
            .values(organization_id=org_id, is_superadmin=(role == "ADMIN"), role="ADMIN")
        )

    for table in ("product", "applicant"):
        owned = sa.table(
            table, sa.column("owner_id", sa.Uuid()), sa.column("organization_id", sa.Uuid())
        )
        bind.execute(
            owned.update().values(
                organization_id=sa.select(user.c.organization_id)
                .where(user.c.id == owned.c.owner_id)
                .scalar_subquery()
            )
        )

    with op.batch_alter_table("user") as batch_op:
        batch_op.alter_column("organization_id", existing_type=sa.Uuid(), nullable=False)
        batch_op.create_foreign_key(
            "fk_user_organization_id", "organization", ["organization_id"], ["id"]
        )
    for table in ("product", "applicant"):
        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column("organization_id", existing_type=sa.Uuid(), nullable=False)
            batch_op.create_foreign_key(
                f"fk_{table}_organization_id", "organization", ["organization_id"], ["id"]
            )


def downgrade() -> None:
    bind = op.get_bind()
    user = sa.table(
        "user",
        sa.column("role", sa.String()),
        sa.column("is_superadmin", sa.Boolean()),
    )
    # The upgrade's mapping reversed: a super-admin was a global ADMIN,
    # everyone else a USER.
    bind.execute(
        user.update().values(
            role=sa.case((user.c.is_superadmin == sa.true(), "ADMIN"), else_="USER")
        )
    )

    for table in ("product", "applicant"):
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_constraint(f"fk_{table}_organization_id", type_="foreignkey")
            batch_op.drop_column("organization_id")
    with op.batch_alter_table("user") as batch_op:
        batch_op.drop_constraint("fk_user_organization_id", type_="foreignkey")
        batch_op.drop_column("is_superadmin")
        batch_op.drop_column("organization_id")
    op.drop_table("organization")
