"""add user role

Adds User.role (Postgres ENUM 'user'/'admin', NOT NULL, default 'user') --
see app/models/enums.py's UserRole WHY. Every existing account becomes a
plain user; there is no self-service or migration path to admin (see
scripts/promote_admin.py).

AUTOGENERATE NOTE: autogenerate also proposed dropping
ix_kb_chunk_embedding_hnsw and ix_sequence_leaf_sequence_id_section_key --
the same recurring false positive noted in d2f747481744 and 64efcb7914f1
(SQLite reflection can't round-trip the pgvector HNSW index or one created
outside model metadata). Both lines were removed by hand.

Revision ID: 241ddbf7bd53
Revises: 64efcb7914f1
Create Date: 2026-09-02

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "241ddbf7bd53"
down_revision: Union[str, Sequence[str], None] = "64efcb7914f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # WHY create the type explicitly first: every prior enum column in this
    # project was born inside a create_table (whose DDL creates the
    # Postgres type as a side effect) or extended an existing one via
    # ALTER TYPE ... ADD VALUE (fed49611d433). This is the first time a
    # brand-new enum-typed column is added via add_column alone, and that
    # path does NOT create the type for you -- omitting this raises
    # "type userrole does not exist" on Postgres (SQLite has no separate
    # type to create, so checkfirst=True is a no-op there).
    role_enum = sa.Enum("USER", "ADMIN", name="userrole")
    role_enum.create(op.get_bind(), checkfirst=True)

    # WHY batch mode: SQLite (test_migration.py) can't ALTER TABLE ADD
    # COLUMN with a NOT NULL constraint in one step the way Postgres can --
    # same reasoning as 64efcb7914f1's owner_id. WHY server_default here
    # (owner_id's migration didn't have one): every existing row gets an
    # unambiguous, correct value ("user") for free -- unlike owner_id there
    # is no real ownership history to reconstruct, so a plain default is
    # the honest answer, not a workaround.
    with op.batch_alter_table("user") as batch_op:
        batch_op.add_column(sa.Column("role", role_enum, nullable=False, server_default="USER"))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("user") as batch_op:
        batch_op.drop_column("role")
    # WHY dialect-guarded: Postgres's ENUM is a real, separate named type
    # that outlives the column that used it (SQLite has no equivalent --
    # sa.Enum compiles there to a plain VARCHAR + CHECK constraint, which
    # drop_column already removed). Left undropped, re-running this
    # migration's upgrade() would fail on "type userrole already exists".
    if op.get_bind().dialect.name == "postgresql":
        sa.Enum(name="userrole").drop(op.get_bind(), checkfirst=True)
