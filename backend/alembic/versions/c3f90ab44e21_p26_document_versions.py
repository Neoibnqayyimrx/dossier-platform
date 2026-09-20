"""P26 document versions

Every file that has ever stood at a leaf, instead of only the latest one.

P18 accepted overwriting as a deliberate simplification, on the grounds
that eCTD lifecycle already versions at the SEQUENCE level. That covers
what was FILED. It does not cover the working copy between two sequences,
where a leaf can be replaced any number of times and each replacement
destroyed its predecessor's bytes irrecoverably -- so "which CPP did we
attach in March, and who replaced it in April?" had no answer.

`section_document` KEEPS its file columns and remains the current version:
every consumer (app/assembly/assemble.py, the lifecycle resolver, the
validation rules) already reads `storage_key` and `md5` off it, and none of
them should have to learn about versioning. See
docs/decisions/0003-document-versioning.md for why that beat an
`is_current` flag.

DATA NOTE -- every existing SectionDocument is backfilled as its own
version 1, copying its columns verbatim INCLUDING its storage key. That key
is the pre-P26 deterministic path (`.../documents/{leaf}.pdf`) rather than
the new per-version path, and it is left exactly as it is: those bytes are
really there, under really that key, and rewriting history to make old rows
look like they followed the new convention would be a lie in the audit
trail this table exists to provide. New uploads write to the versioned
path; version 1 of a pre-existing document points where it always pointed.

Revision ID: c3f90ab44e21
Revises: f5c8b21a90d7
Create Date: 2026-09-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c3f90ab44e21"
down_revision = "f5c8b21a90d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_version",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("section_document_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("md5", sa.String(length=32), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(length=300), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("uploaded_by_id", sa.Uuid(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["section_document_id"], ["section_document.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "section_document_id", "version_number", name="uq_document_version_number"
        ),
    )

    _backfill_one_version_per_existing_document()


def downgrade() -> None:
    op.drop_table("document_version")


def _backfill_one_version_per_existing_document() -> None:
    """Give every already-attached document a version 1 describing itself.

    WHY backfill rather than starting the history at the next upload: a
    leaf whose history begins at version 2 reads as though version 1 was
    lost. It was not -- it is the file currently attached, and saying so is
    the honest record.

    WHY a text INSERT..SELECT rather than reading rows into Python and
    bulk-inserting them: the round trip re-marshals every value through
    SQLAlchemy's type system, and the types that come back differ by
    dialect -- Postgres hands back UUID and datetime objects, SQLite hands
    back strings. Binding those to sa.Uuid()/sa.DateTime() columns raised
    mid-migration ("'str' object has no attribute 'hex'", then "SQLite
    DateTime type only accepts Python datetime"). Letting the database copy
    its own rows sidesteps the question entirely: the values never leave
    it, so there is nothing to convert and nothing to get wrong.

    The ids are the one thing Python must supply, since `gen_random_uuid()`
    is Postgres-only and SQLite has no equivalent.
    """
    import uuid as _uuid

    bind = op.get_bind()
    document_ids = [row.id for row in bind.execute(sa.text("SELECT id FROM section_document"))]
    if not document_ids:
        return

    bind.execute(
        sa.text(
            "INSERT INTO document_version ("
            "  id, section_document_id, version_number, storage_key, md5,"
            "  size_bytes, original_filename, content_type, uploaded_by_id,"
            "  uploaded_at, created_at, updated_at"
            ") SELECT"
            "  :new_id, id, 1, storage_key, md5,"
            "  size_bytes, original_filename, content_type, uploaded_by_id,"
            # The version's timestamps are the DOCUMENT's: this row records
            # an upload that happened then, not a migration that ran now.
            "  uploaded_at, uploaded_at, uploaded_at"
            " FROM section_document WHERE id = :document_id"
        ),
        [
            {"new_id": str(_uuid.uuid4()), "document_id": document_id}
            for document_id in document_ids
        ],
    )
