"""P19 data-ready sections: excipient origin, packaging role, TSE/BSE certificate

Revision ID: e5b3a91c47d0
Revises: c83b1d4e7a55
Create Date: 2026-09-06 09:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e5b3a91c47d0"
down_revision: Union[str, Sequence[str], None] = "c83b1d4e7a55"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Same "ALTER TYPE ADD VALUE, dialect-guarded" pattern as c83b1d4e7a55:
# autogenerate never detects added enum labels, and SQLite (which every
# test uses) has no native enum type to alter.
NEW_CERTIFICATE_TYPES = ["TSE_BSE"]

EXCIPIENT_ORIGIN = sa.Enum(
    "SYNTHETIC", "MINERAL", "PLANT", "ANIMAL", "HUMAN", name="excipientorigin"
)
PACKAGING_ROLE = sa.Enum("DRUG_PRODUCT", "DRUG_SUBSTANCE", name="packagingrole")


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    # `create` with checkfirst is a no-op on SQLite (no native enum type)
    # and creates the type once on PostgreSQL. Doing it explicitly rather
    # than leaving it to add_column keeps the DOWN path able to drop it.
    EXCIPIENT_ORIGIN.create(bind, checkfirst=True)
    PACKAGING_ROLE.create(bind, checkfirst=True)

    op.add_column("excipient", sa.Column("origin", EXCIPIENT_ORIGIN, nullable=True))
    op.add_column(
        "packaging",
        sa.Column("active_ingredient_id", sa.Uuid(), nullable=True),
    )
    # WHY a server_default here when the model declares a Python-side
    # default: existing rows have no value, and every one of them describes
    # the finished product -- 3.2.S.6 did not exist when they were written,
    # so nothing on file can have meant "drug substance". The default is
    # then dropped, so a future insert that omits the role fails loudly
    # rather than silently becoming drug-product packaging.
    op.add_column(
        "packaging",
        sa.Column("role", PACKAGING_ROLE, nullable=False, server_default="DRUG_PRODUCT"),
    )
    with op.batch_alter_table("packaging") as batch:
        batch.alter_column("role", server_default=None)
        batch.create_foreign_key(
            "fk_packaging_active_ingredient_id",
            "active_ingredient",
            ["active_ingredient_id"],
            ["id"],
        )

    if bind.dialect.name == "postgresql":
        for value in NEW_CERTIFICATE_TYPES:
            op.execute(f"ALTER TYPE certificatetype ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("packaging") as batch:
        batch.drop_constraint("fk_packaging_active_ingredient_id", type_="foreignkey")
    op.drop_column("packaging", "role")
    op.drop_column("packaging", "active_ingredient_id")
    op.drop_column("excipient", "origin")

    bind = op.get_bind()
    PACKAGING_ROLE.drop(bind, checkfirst=True)
    EXCIPIENT_ORIGIN.drop(bind, checkfirst=True)
    # The certificate enum label is deliberately not removed: PostgreSQL
    # cannot drop a value from an enum type (see c83b1d4e7a55).
