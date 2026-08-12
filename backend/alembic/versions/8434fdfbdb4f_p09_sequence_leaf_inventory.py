"""P09 sequence leaf inventory

Revision ID: 8434fdfbdb4f
Revises: fed49611d433
Create Date: 2026-08-12 11:29:21.459201

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8434fdfbdb4f'
down_revision: Union[str, Sequence[str], None] = 'fed49611d433'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# WHY the HNSW index drop/recreate that autogenerate proposed here is
# omitted: SQLAlchemy's reflection can't see pgvector's HNSW index options
# (postgresql_ops/postgresql_using) the same way it wrote them, so every
# autogenerate against a live Postgres re-detects P03's `kb_chunk` HNSW
# index as "removed" even though nothing about it changed. Same class of
# false positive as the "autogenerate never detects added enum labels"
# note on 1c06948fcf0b -- reflection has known blind spots around
# extension-specific DDL, so each migration must be read, not trusted
# blind. Left untouched here; unrelated to this table.


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "sequence_leaf",
        sa.Column("sequence_id", sa.Uuid(), nullable=False),
        sa.Column("section_key", sa.String(length=100), nullable=False),
        sa.Column("leaf_id", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("checksum", sa.String(length=32), nullable=False),
        sa.Column("operation", sa.String(length=10), nullable=False),
        sa.Column("modified_file", sa.String(length=600), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["sequence_id"], ["sequence.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    # The lifecycle resolver's one query is "give me sequence X's leaves by
    # section_key" -- index the pair it actually filters on.
    op.create_index(
        "ix_sequence_leaf_sequence_id_section_key",
        "sequence_leaf",
        ["sequence_id", "section_key"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_sequence_leaf_sequence_id_section_key", table_name="sequence_leaf")
    op.drop_table("sequence_leaf")
