"""add applicant owner

Adds Applicant.owner_id (FK -> user.id, NOT NULL) -- the second owned
root of master data, after Product (see app/models/applicant.py's WHY).
An Applicant is created directly through /applicants rather than through
a Product, so it has no owner to borrow the way a certificate or a
declaration does.

DATA NOTE: existing applicant rows DO have a recoverable owner, unlike
the Product backfill in 64efcb7914f1 -- an applicant is reached from the
project that names it, and that project's product already carries an
owner. So the backfill follows the real relationship
(applicant <- project -> product.owner_id) and only falls back to the
earliest account for an orphan applicant no project points at.

AUTOGENERATE NOTE: autogenerate also proposed dropping
ix_kb_chunk_embedding_hnsw and ix_sequence_leaf_sequence_id_section_key --
the same recurring false positive noted in d2f747481744, 64efcb7914f1 and
241ddbf7bd53 (SQLite reflection can't round-trip the pgvector HNSW index
or one created outside model metadata). Both lines were removed by hand.

Revision ID: 750cee7cc614
Revises: 241ddbf7bd53
Create Date: 2026-09-04

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "750cee7cc614"
down_revision: Union[str, Sequence[str], None] = "241ddbf7bd53"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # WHY batch mode + nullable first, then backfill, then NOT NULL: the
    # same three-step dance as 64efcb7914f1's owner_id -- SQLite (used by
    # test_migration.py) can't ALTER TABLE ADD CONSTRAINT, and existing
    # rows need a value before the column can be made NOT NULL.
    with op.batch_alter_table("applicant") as batch_op:
        batch_op.add_column(sa.Column("owner_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key("fk_applicant_owner_id", "user", ["owner_id"], ["id"])

    # The real relationship first: whoever owns the product of a project
    # that names this applicant.
    op.execute("""
        UPDATE applicant
        SET owner_id = (
            SELECT product.owner_id
            FROM project
            JOIN product ON product.id = project.product_id
            WHERE project.applicant_id = applicant.id
            ORDER BY project.created_at
            LIMIT 1
        )
        WHERE owner_id IS NULL
        """)
    # Only then the fallback, for an applicant no project points at.
    op.execute("""
        UPDATE applicant
        SET owner_id = (SELECT id FROM "user" ORDER BY created_at LIMIT 1)
        WHERE owner_id IS NULL
        """)

    with op.batch_alter_table("applicant") as batch_op:
        batch_op.alter_column("owner_id", nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("applicant") as batch_op:
        batch_op.drop_constraint("fk_applicant_owner_id", type_="foreignkey")
        batch_op.drop_column("owner_id")
