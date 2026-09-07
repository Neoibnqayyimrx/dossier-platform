"""P21 stability axes and timepoint results

Two changes, one migration, because they are one design (see
app/models/stability.py):

1. `stability_study` gains the axes a real study has and loses the one it
   never had a right to assume:
     - `active_ingredient_id`, and `product_id` becomes NULLABLE, with a
       CHECK that exactly one is set. A study is a study OF the drug
       substance (3.2.S.7) or OF the finished product (3.2.P.8).
     - `batch_analysis_id` -- which batch it was run on, as a foreign key
       to the batch whose analysis 3.2.S.4.4 / 3.2.P.5.4 already files.
     - `packaging_id` -- which pack presentation it was stored in.
2. `stability_result` -- one test, at one timepoint, in one study,
   foreign-keyed to the `specification_test` whose limit judges it.

DATA NOTE. **No existing row moves.** Every study on file stays a
drug-product study with the `product_id` it already had, so the CHECK is
satisfied by every pre-existing row before it is added, and R05's existing
tests keep their fixtures unchanged. This is the same widening move
a7d31f905c42 made for `specification_test`.

THE ONE DESTRUCTIVE-LOOKING CHANGE, and why it is not: `result_summary`
is RENAMED to `notes`, not dropped. Its content is the filer's own text
and this migration will not throw it away -- but it stops being the
section's answer. 3.2.S.7.1 and 3.2.P.8.1 are now built from the timepoint
results, because a typed summary printed above a computed table is exactly
the contradiction this phase exists to remove: the sentence can say "within
specification through 24 months" while the table below shows dissolution
failing at 6. The text survives as a note; the conclusion is computed.

It also becomes NULLABLE, since a study entered as a grid of timepoints
owes no prose at all.

WHY `batch_alter_table`: SQLite (which every test and the local slice run
on) cannot ALTER or RENAME a column in place, so Alembic rebuilds the
table; on PostgreSQL the same calls emit plain ALTERs. Same code, both
dialects -- the pattern a7d31f905c42 and e5b3a91c47d0 already use.

Revision ID: b3f8c21d90ae
Revises: a7d31f905c42
Create Date: 2026-09-06 20:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b3f8c21d90ae"
down_revision: Union[str, Sequence[str], None] = "a7d31f905c42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ONE_OWNER_TWO = (
    "(CASE WHEN active_ingredient_id IS NULL THEN 0 ELSE 1 END) + "
    "(CASE WHEN product_id IS NULL THEN 0 ELSE 1 END) = 1"
)


def _base_columns() -> list[sa.Column]:
    """The three columns every table inherits from app.models.base.Base."""
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


def upgrade() -> None:
    """Upgrade schema."""
    # ---- 1. widen stability_study --------------------------------------
    op.add_column("stability_study", sa.Column("active_ingredient_id", sa.Uuid(), nullable=True))
    op.add_column("stability_study", sa.Column("batch_analysis_id", sa.Uuid(), nullable=True))
    op.add_column("stability_study", sa.Column("packaging_id", sa.Uuid(), nullable=True))
    with op.batch_alter_table("stability_study") as batch:
        batch.alter_column("product_id", existing_type=sa.Uuid(), nullable=True)
        batch.alter_column(
            "result_summary",
            new_column_name="notes",
            existing_type=sa.Text(),
            nullable=True,
        )
        batch.create_foreign_key(
            "fk_stability_study_active_ingredient_id",
            "active_ingredient",
            ["active_ingredient_id"],
            ["id"],
        )
        batch.create_foreign_key(
            "fk_stability_study_batch_analysis_id",
            "batch_analysis",
            ["batch_analysis_id"],
            ["id"],
        )
        batch.create_foreign_key(
            "fk_stability_study_packaging_id", "packaging", ["packaging_id"], ["id"]
        )
        batch.create_check_constraint("ck_stability_study_one_owner", ONE_OWNER_TWO)

    # ---- 2. timepoint results ------------------------------------------
    op.create_table(
        "stability_result",
        sa.Column("stability_study_id", sa.Uuid(), nullable=False),
        # NOT nullable, and it is the whole design: a stability result
        # exists to answer a specification test. Without the test there is
        # no limit, and a number with no limit cannot justify a shelf life.
        sa.Column("specification_test_id", sa.Uuid(), nullable=False),
        sa.Column("timepoint_months", sa.Integer(), nullable=False),
        sa.Column("result", sa.String(length=300), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        *_base_columns(),
        sa.ForeignKeyConstraint(["stability_study_id"], ["stability_study.id"]),
        sa.ForeignKeyConstraint(["specification_test_id"], ["specification_test.id"]),
        sa.PrimaryKeyConstraint("id"),
        # One answer per test per timepoint per study. Two rows for the
        # same cell is not extra data, it is a table with two values in one
        # box -- and whichever renders second wins silently.
        sa.UniqueConstraint(
            "stability_study_id",
            "specification_test_id",
            "timepoint_months",
            name="uq_stability_result_cell",
        ),
    )


def downgrade() -> None:
    """Downgrade schema.

    The narrowing direction is the lossy one and says so rather than
    silently discarding: a drug-substance study has nowhere to go in the
    pre-P21 table, whose `product_id` is NOT NULL. Refusing is the same
    call a7d31f905c42's downgrade makes -- this migration will not delete a
    filer's stability data on their behalf.
    """
    bind = op.get_bind()
    orphaned = bind.execute(
        sa.text("SELECT COUNT(*) FROM stability_study WHERE active_ingredient_id IS NOT NULL")
    ).scalar_one()
    if orphaned:
        raise RuntimeError(
            f"{orphaned} stability_study row(s) belong to a drug substance, which the "
            "pre-P21 table cannot represent. Move or delete them deliberately before "
            "downgrading."
        )

    op.drop_table("stability_result")
    # Backfill before the NOT NULL below: a study entered as a grid owes no
    # prose, so its `notes` is legitimately NULL, and the pre-P21 column
    # forbids that. Emptying it is the only honest answer -- inventing a
    # summary sentence here would put text nobody wrote into a section.
    bind.execute(sa.text("UPDATE stability_study SET notes = '' WHERE notes IS NULL"))
    with op.batch_alter_table("stability_study") as batch:
        batch.drop_constraint("ck_stability_study_one_owner", type_="check")
        batch.drop_constraint("fk_stability_study_packaging_id", type_="foreignkey")
        batch.drop_constraint("fk_stability_study_batch_analysis_id", type_="foreignkey")
        batch.drop_constraint("fk_stability_study_active_ingredient_id", type_="foreignkey")
        # NOT NULL again, and the empty string rather than NULL for the
        # rows a grid-entered study left with no prose: the pre-P21 column
        # is NOT NULL, and inventing a summary sentence here would put text
        # nobody wrote into a dossier section.
        batch.alter_column(
            "notes",
            new_column_name="result_summary",
            existing_type=sa.Text(),
            nullable=False,
            server_default="",
        )
        batch.alter_column("product_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_column("stability_study", "packaging_id")
    op.drop_column("stability_study", "batch_analysis_id")
    op.drop_column("stability_study", "active_ingredient_id")
