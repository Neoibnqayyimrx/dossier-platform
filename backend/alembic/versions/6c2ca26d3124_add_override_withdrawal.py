"""add override withdrawal

Adds ValidationOverride.withdrawn_at / withdrawn_by_id (both nullable) --
retracting an override without erasing it. See the model's WHY: the row
IS the audit trail, so withdrawal is a new fact written on it rather than
a DELETE that would destroy the record of a decision a human once made,
and the reason they gave.

Both nullable with no backfill: every existing override is, by
definition, still standing.

AUTOGENERATE NOTE: autogenerate again proposed dropping
ix_kb_chunk_embedding_hnsw and ix_sequence_leaf_sequence_id_section_key --
the same recurring false positive noted in d2f747481744, 64efcb7914f1,
241ddbf7bd53 and 750cee7cc614 (SQLite reflection can't round-trip the
pgvector HNSW index or one created outside model metadata). Both lines
were removed by hand, from upgrade() and from downgrade().

Revision ID: 6c2ca26d3124
Revises: 750cee7cc614
Create Date: 2026-09-04

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "6c2ca26d3124"
down_revision: Union[str, Sequence[str], None] = "750cee7cc614"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # WHY batch mode: SQLite (test_migration.py) can't ALTER TABLE ADD
    # CONSTRAINT -- same reasoning as every other FK added in this project.
    with op.batch_alter_table("validation_override") as batch_op:
        batch_op.add_column(sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("withdrawn_by_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_validation_override_withdrawn_by_id", "user", ["withdrawn_by_id"], ["id"]
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("validation_override") as batch_op:
        batch_op.drop_constraint("fk_validation_override_withdrawn_by_id", type_="foreignkey")
        batch_op.drop_column("withdrawn_by_id")
        batch_op.drop_column("withdrawn_at")
