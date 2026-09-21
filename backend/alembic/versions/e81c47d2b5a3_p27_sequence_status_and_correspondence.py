"""P27 sequence status, submission-unit type, and correspondence

Three additions, all answering the same gap: a registration is a
CONVERSATION, and the platform could only model the packages.

1. `sequence.status` -- where a sequence stands with the agency. Before
   this a Sequence carried `submitted_at` and nothing else, so the only two
   states distinguishable were "has a date" and "has not". Moved through a
   dedicated endpoint that enforces legal transitions, not by PATCH.

2. `sequence.submission_unit_type` -- what KIND of transaction this
   sequence is, using the EU regional DTD's own vocabulary for
   `submission-unit/@type`. This one FIXES A BUG rather than only adding a
   field: `app/ectd/regional.py` hardcoded "initial" for every sequence, so
   a response to a deficiency letter was filed telling the agency it was a
   fresh submission. DTD-valid, and wrong.

3. `correspondence` -- deficiency letters, queries, responses and
   commitments, with the due date that makes them urgent. Missing a
   response deadline can lapse an application: the dossier is fine and the
   registration is lost on a date, and nothing in the schema could say so.

DATA NOTE -- both new sequence columns take server defaults, so existing
rows become DRAFT/initial without a backfill pass. That is the honest
reading of an existing row in both cases: a sequence the platform has been
tracking with no status information is exactly a draft, and "initial" is
what every pre-P27 sequence was already being filed as, so the default
preserves the behaviour rather than silently changing what a rebuild would
produce.

Revision ID: e81c47d2b5a3
Revises: c3f90ab44e21
Create Date: 2026-09-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e81c47d2b5a3"
down_revision = "c3f90ab44e21"
branch_labels = None
depends_on = None

# WHY the enum types are spelled out here rather than imported from
# app.models.enums: a migration is a historical record of the schema at a
# point in time. Importing the live enum would make this migration change
# meaning the next time someone adds a value to it, and an old database
# would then upgrade to a shape this revision never described.
SEQUENCE_STATUS = sa.Enum(
    "DRAFT",
    "BUILT",
    "SUBMITTED",
    "ACKNOWLEDGED",
    "UNDER_REVIEW",
    "APPROVED",
    "REJECTED",
    name="sequencestatus",
)
SUBMISSION_UNIT_TYPE = sa.Enum(
    "INITIAL",
    "VALIDATION_RESPONSE",
    "RESPONSE",
    "ADDITIONAL_INFO",
    "CLOSING",
    "CONSOLIDATING",
    "CORRIGENDUM",
    "REFORMAT",
    "RE_EXAMINATION",
    name="submissionunittype",
)
CORRESPONDENCE_DIRECTION = sa.Enum("INBOUND", "OUTBOUND", name="correspondencedirection")
CORRESPONDENCE_TYPE = sa.Enum(
    "DEFICIENCY_LETTER",
    "QUERY",
    "RESPONSE",
    "COMMITMENT",
    "OTHER",
    name="correspondencetype",
)
CORRESPONDENCE_STATUS = sa.Enum("OPEN", "CLOSED", name="correspondencestatus")


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in (
        SEQUENCE_STATUS,
        SUBMISSION_UNIT_TYPE,
        CORRESPONDENCE_DIRECTION,
        CORRESPONDENCE_TYPE,
        CORRESPONDENCE_STATUS,
    ):
        # No-op on SQLite, which has no CREATE TYPE; required on Postgres,
        # where add_column would otherwise reference a type that does not
        # exist yet.
        enum_type.create(bind, checkfirst=True)

    # batch_alter_table: SQLite cannot ALTER TABLE ADD CONSTRAINT or add a
    # column with a non-trivial default in place, and tests/test_migration.py
    # runs these against SQLite. Batch mode recreates there and issues plain
    # ALTERs on Postgres.
    with op.batch_alter_table("sequence") as batch_op:
        batch_op.add_column(
            sa.Column(
                "status",
                SEQUENCE_STATUS,
                nullable=False,
                server_default="DRAFT",
            )
        )
        batch_op.add_column(
            sa.Column(
                "submission_unit_type",
                SUBMISSION_UNIT_TYPE,
                nullable=False,
                server_default="INITIAL",
            )
        )

    op.create_table(
        "correspondence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        # Nullable: plenty of correspondence has no sequence to point at --
        # a pre-submission meeting request, a fee notice. SET NULL rather
        # than CASCADE so deleting a sequence does not destroy the record
        # of the agency's letter about it.
        sa.Column("sequence_id", sa.Uuid(), nullable=True),
        sa.Column("direction", CORRESPONDENCE_DIRECTION, nullable=False),
        sa.Column("correspondence_type", CORRESPONDENCE_TYPE, nullable=False),
        sa.Column("subject", sa.String(length=300), nullable=False),
        sa.Column("received_or_sent_at", sa.DateTime(timezone=True), nullable=False),
        # Date, not DateTime: an agency's deadline is "by 14 March", never
        # "by 14 March at 16:20".
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", CORRESPONDENCE_STATUS, nullable=False, server_default="OPEN"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("section_document_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.ForeignKeyConstraint(["sequence_id"], ["sequence.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["section_document_id"], ["section_document.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("correspondence")
    with op.batch_alter_table("sequence") as batch_op:
        batch_op.drop_column("submission_unit_type")
        batch_op.drop_column("status")

    bind = op.get_bind()
    for enum_type in (
        CORRESPONDENCE_STATUS,
        CORRESPONDENCE_TYPE,
        CORRESPONDENCE_DIRECTION,
        SUBMISSION_UNIT_TYPE,
        SEQUENCE_STATUS,
    ):
        enum_type.drop(bind, checkfirst=True)
