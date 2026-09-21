"""gap Phase 4b: the identifiers FDA's Module 1 backbone carries

Three nullable columns, all read by `app/ectd/us_regional.py` and all
required for an FDA export by rule R34 rather than by the schema:

1. `applicant.duns_number` -- FDA's backbone names the applicant by its
   nine-digit D-U-N-S number on every submission. On the applicant because
   it identifies the legal entity, not the filing.

2. `project.application_number` -- the number the agency assigned to the
   application ("ANDA 123456" -> "123456"). Issued by the agency, so it is
   entered, never generated.

3. `project.fda_application_type` -- NDA, ANDA or BLA, i.e. what that number
   numbers.

WHY nullable, all three: only FDA asks for them, and a project exists long
before an agency has issued it anything. Completeness for an FDA filing is a
validation question (R34), the same call R14 makes for a NAFDAC applicant.

WHY the last two are on `project` although gap.md Phase 6 will introduce an
`Application` entity: Phase 6 is the natural home and will move them. Adding
that entity here would pre-empt a phase the user sequenced deliberately.

DATA NOTE -- no backfill: nothing existing has these values, and inventing
them is exactly what this phase refuses to do.

Revision ID: a7d4c1f09e62
Revises: e81c47d2b5a3
Create Date: 2026-09-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a7d4c1f09e62"
down_revision = "e81c47d2b5a3"
branch_labels = None
depends_on = None

# Spelled out, not imported from app.models.enums -- see the P27 migration
# for why a migration must not change meaning when a live enum does.
FDA_APPLICATION_TYPE = sa.Enum("NDA", "ANDA", "BLA", name="fdaapplicationtype")


def upgrade() -> None:
    # No-op on SQLite; required on Postgres before a column can use the type.
    FDA_APPLICATION_TYPE.create(op.get_bind(), checkfirst=True)

    with op.batch_alter_table("applicant") as batch_op:
        batch_op.add_column(sa.Column("duns_number", sa.String(length=9), nullable=True))

    with op.batch_alter_table("project") as batch_op:
        batch_op.add_column(sa.Column("application_number", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("fda_application_type", FDA_APPLICATION_TYPE, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("project") as batch_op:
        batch_op.drop_column("fda_application_type")
        batch_op.drop_column("application_number")

    with op.batch_alter_table("applicant") as batch_op:
        batch_op.drop_column("duns_number")

    FDA_APPLICATION_TYPE.drop(op.get_bind(), checkfirst=True)
