"""P18 upload path: section_document table and three certificate types

Revision ID: c83b1d4e7a55
Revises: a41f9c7b6e02
Create Date: 2026-09-04 23:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c83b1d4e7a55"
down_revision: Union[str, Sequence[str], None] = "a41f9c7b6e02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Same "ALTER TYPE ADD VALUE, dialect-guarded" pattern as fed49611d433 and
# 1c06948fcf0b: autogenerate never detects added enum labels, and SQLite
# (which every test uses) has no native enum type to alter.
NEW_CERTIFICATE_TYPES = ["INCORPORATION", "PHARMACIST_LICENCE", "PREMISES_REGISTRATION"]


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "section_document",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("section_number", sa.String(length=20), nullable=False),
        sa.Column("subject_slug", sa.String(length=120), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("md5", sa.String(length=32), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(length=300), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("uploaded_by_id", sa.Uuid(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        # One document per leaf: two rows here would mean two files at one
        # path in the package, which is a corrupt submission rather than a
        # merely confusing one. See the model's docstring for why
        # subject_slug is "" and never NULL -- a UNIQUE over a nullable
        # column would not actually stop the duplicate.
        sa.UniqueConstraint(
            "project_id", "section_number", "subject_slug", name="uq_section_document_leaf"
        ),
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for value in NEW_CERTIFICATE_TYPES:
            op.execute(f"ALTER TYPE certificatetype ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    """Downgrade schema."""
    # The enum labels are deliberately not removed: PostgreSQL cannot drop a
    # value from an enum type, and any row already using one would be
    # orphaned by a type swap. Dropping the table is the reversible half.
    op.drop_table("section_document")
