"""P17 applicability: submission type and conditional answers on project

Revision ID: a41f9c7b6e02
Revises: 6c2ca26d3124
Create Date: 2026-09-04 09:40:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a41f9c7b6e02"
down_revision: Union[str, Sequence[str], None] = "6c2ca26d3124"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SUBMISSION_TYPE = sa.Enum("MULTISOURCE_GENERIC", "NEW_CHEMICAL_ENTITY", name="submissiontype")


def upgrade() -> None:
    """Upgrade schema."""
    # WHY create_type + an explicit server_default on the column: every
    # project that already exists was built on the assumption this enum now
    # names -- a multisource generic filing -- so backfilling it is not a
    # guess, it is writing down what was already true. A nullable column
    # would leave "we don't know the scope of this dossier" as a
    # representable state, which is exactly what P17 removes.
    SUBMISSION_TYPE.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "project",
        sa.Column(
            "submission_type",
            SUBMISSION_TYPE,
            nullable=False,
            server_default="MULTISOURCE_GENERIC",
        ),
    )
    op.add_column(
        "project",
        sa.Column(
            "condition_answers",
            sa.JSON(),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("project", "condition_answers")
    op.drop_column("project", "submission_type")
    SUBMISSION_TYPE.drop(op.get_bind(), checkfirst=True)
