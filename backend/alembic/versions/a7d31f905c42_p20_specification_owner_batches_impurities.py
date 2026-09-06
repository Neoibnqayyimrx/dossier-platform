"""P20 polymorphic specification owner, batch analyses, impurities

Three changes, one migration, because they are one design:

1. `specification_test` gains `product_id` and `excipient_id`, its
   `active_ingredient_id` becomes NULLABLE, and a CHECK constraint says
   exactly one of the three is set. See app/models/spec_owner.py for why
   this shape rather than an `owner_type` + `owner_id` discriminator.
2. `batch_analysis` + `batch_analysis_result` (3.2.S.4.4, 3.2.P.5.4).
3. `impurity` (3.2.S.3.2, 3.2.P.5.5).

DATA NOTE -- and this is the important one. **No existing row moves.**
Every `specification_test` on file today belongs to a drug substance and
keeps the exact `active_ingredient_id` it already had; the migration only
WIDENS the table. That is what makes P13's drug-substance behaviour, and
its tests, survive unchanged -- the prompt's fourth definition-of-done.

The CHECK constraint is therefore satisfied by every pre-existing row
before it is added: one owner set, two nulls. It is added last for that
reason -- adding it first would validate against a table whose new columns
did not exist yet.

WHY `batch_alter_table` for the nullability change: SQLite (which every
test and the local slice run on) cannot ALTER a column in place, so Alembic
rebuilds the table. On PostgreSQL the same call emits a plain ALTER. Same
code, both dialects -- the pattern e5b3a91c47d0 already uses.

Revision ID: a7d31f905c42
Revises: e5b3a91c47d0
Create Date: 2026-09-06 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a7d31f905c42"
down_revision: Union[str, Sequence[str], None] = "e5b3a91c47d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

IMPURITY_TYPE = sa.Enum(
    "PROCESS_RELATED",
    "DEGRADATION",
    "RESIDUAL_SOLVENT",
    "INORGANIC",
    name="impuritytype",
)

# Written out once rather than repeated in three create_table calls: the
# three timestamp/id columns every table inherits from app.models.base.Base.
def _base_columns() -> list[sa.Column]:
    return [
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
    ]


ONE_OWNER_THREE = (
    "(CASE WHEN active_ingredient_id IS NULL THEN 0 ELSE 1 END) + "
    "(CASE WHEN product_id IS NULL THEN 0 ELSE 1 END) + "
    "(CASE WHEN excipient_id IS NULL THEN 0 ELSE 1 END) = 1"
)
ONE_OWNER_TWO = (
    "(CASE WHEN active_ingredient_id IS NULL THEN 0 ELSE 1 END) + "
    "(CASE WHEN product_id IS NULL THEN 0 ELSE 1 END) = 1"
)


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    IMPURITY_TYPE.create(bind, checkfirst=True)

    # ---- 1. widen specification_test -----------------------------------
    op.add_column("specification_test", sa.Column("product_id", sa.Uuid(), nullable=True))
    op.add_column("specification_test", sa.Column("excipient_id", sa.Uuid(), nullable=True))
    with op.batch_alter_table("specification_test") as batch:
        batch.alter_column("active_ingredient_id", existing_type=sa.Uuid(), nullable=True)
        batch.create_foreign_key(
            "fk_specification_test_product_id", "product", ["product_id"], ["id"]
        )
        batch.create_foreign_key(
            "fk_specification_test_excipient_id", "excipient", ["excipient_id"], ["id"]
        )
        batch.create_check_constraint("ck_specification_test_one_owner", ONE_OWNER_THREE)

    # ---- 2. batch analyses ---------------------------------------------
    op.create_table(
        "batch_analysis",
        sa.Column("active_ingredient_id", sa.Uuid(), nullable=True),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("batch_number", sa.String(length=80), nullable=False),
        sa.Column("manufacture_date", sa.Date(), nullable=True),
        sa.Column("batch_size", sa.String(length=120), nullable=True),
        sa.Column("manufacturer_id", sa.Uuid(), nullable=True),
        sa.Column("purpose", sa.String(length=200), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_base_columns(),
        sa.ForeignKeyConstraint(["active_ingredient_id"], ["active_ingredient.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"]),
        sa.ForeignKeyConstraint(["manufacturer_id"], ["manufacturer.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(ONE_OWNER_TWO, name="ck_batch_analysis_one_owner"),
    )
    op.create_table(
        "batch_analysis_result",
        sa.Column("batch_analysis_id", sa.Uuid(), nullable=False),
        sa.Column("specification_test_id", sa.Uuid(), nullable=False),
        sa.Column("result", sa.String(length=300), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        *_base_columns(),
        sa.ForeignKeyConstraint(["batch_analysis_id"], ["batch_analysis.id"]),
        # NOT nullable, and that is the design: a result exists to answer a
        # specification test. Without the test there is no limit, and a
        # number with no limit is not a result -- it is a rumour.
        sa.ForeignKeyConstraint(["specification_test_id"], ["specification_test.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # ---- 3. impurities --------------------------------------------------
    op.create_table(
        "impurity",
        sa.Column("active_ingredient_id", sa.Uuid(), nullable=True),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("impurity_type", IMPURITY_TYPE, nullable=False),
        sa.Column("limit", sa.String(length=120), nullable=True),
        sa.Column("limit_source", sa.String(length=200), nullable=True),
        sa.Column("smiles", sa.String(length=500), nullable=True),
        sa.Column("origin", sa.Text(), nullable=True),
        *_base_columns(),
        sa.ForeignKeyConstraint(["active_ingredient_id"], ["active_ingredient.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(ONE_OWNER_TWO, name="ck_impurity_one_owner"),
    )


def downgrade() -> None:
    """Downgrade schema.

    The narrowing direction is the lossy one, and it says so rather than
    silently discarding: a drug-product or excipient specification row has
    nowhere to go in the pre-P20 table, so the downgrade refuses while any
    exists instead of deleting a filer's specification.
    """
    bind = op.get_bind()
    orphaned = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM specification_test "
            "WHERE product_id IS NOT NULL OR excipient_id IS NOT NULL"
        )
    ).scalar_one()
    if orphaned:
        raise RuntimeError(
            f"{orphaned} specification_test row(s) belong to a drug product or an "
            "excipient, which the pre-P20 table cannot represent. Move or delete "
            "them deliberately before downgrading -- this migration will not drop "
            "a specification on your behalf."
        )

    op.drop_table("impurity")
    op.drop_table("batch_analysis_result")
    op.drop_table("batch_analysis")
    IMPURITY_TYPE.drop(bind, checkfirst=True)

    with op.batch_alter_table("specification_test") as batch:
        batch.drop_constraint("ck_specification_test_one_owner", type_="check")
        batch.drop_constraint("fk_specification_test_excipient_id", type_="foreignkey")
        batch.drop_constraint("fk_specification_test_product_id", type_="foreignkey")
        batch.alter_column("active_ingredient_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_column("specification_test", "excipient_id")
    op.drop_column("specification_test", "product_id")
