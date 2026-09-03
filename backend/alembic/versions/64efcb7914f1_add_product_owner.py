"""add product owner

Adds Product.owner_id (FK -> user.id, NOT NULL) -- the root of per-user
authorization (see app/models/product.py's WHY). Every Project and every
child resource is reached by walking Product, so this one column is what
every ownership check in the API routers joins through.

DATA NOTE: dev/demo Product rows already exist with no real "owner" on
file (they predate this concept). Backfilling them to the true creator
isn't possible -- that history was never recorded -- so they're assigned
to the earliest-created user as a dev-data convenience, not a
reconstruction of real ownership. A platform with real applicant data
would need a hand-picked backfill instead of this default.

AUTOGENERATE NOTE: autogenerate also proposed dropping
ix_kb_chunk_embedding_hnsw and ix_sequence_leaf_sequence_id_section_key --
the same recurring false positive noted in d2f747481744 (SQLite reflection
can't round-trip the pgvector HNSW index or one created outside model
metadata). Both lines were removed by hand.

Revision ID: 64efcb7914f1
Revises: d2f747481744
Create Date: 2026-09-01

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "64efcb7914f1"
down_revision: Union[str, Sequence[str], None] = "d2f747481744"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # WHY batch mode: SQLite (used by test_migration.py) can't ALTER TABLE
    # ADD CONSTRAINT -- same reasoning as fed49611d433's applicant_id FK.
    # WHY nullable=True first: existing Product rows need a value before
    # the column can be made NOT NULL (see DATA NOTE above); a bare
    # NOT NULL add would fail against the live dev database.
    with op.batch_alter_table("product") as batch_op:
        batch_op.add_column(sa.Column("owner_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key("fk_product_owner_id", "user", ["owner_id"], ["id"])

    op.execute("""
        UPDATE product
        SET owner_id = (SELECT id FROM "user" ORDER BY created_at LIMIT 1)
        WHERE owner_id IS NULL
        """)

    with op.batch_alter_table("product") as batch_op:
        batch_op.alter_column("owner_id", nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("product") as batch_op:
        batch_op.drop_constraint("fk_product_owner_id", type_="foreignkey")
        batch_op.drop_column("owner_id")
