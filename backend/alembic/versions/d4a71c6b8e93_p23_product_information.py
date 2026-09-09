"""P23 product information

One table, and the interesting part of it is the columns it does NOT have.

`product_information` holds the SmPC's authored clinical particulars --
sections 4.1 to 4.9, plus 6.2 and 6.6 -- one column per numbered section.
It holds no shelf life, no storage condition, no strength and no pack size,
because those already exist on `product`, `packaging` and the stability
data, and the three documents rendered from this row (1.3.1 SmPC, 1.3.2
labelling, 1.3.3 patient leaflet) compute them at render time from those
tables (app/templating/product_information.py).

That absence is the phase. A `shelf_life_months` column here would restore
in one migration exactly the defect P23 exists to remove: three documents
each holding their own copy of a number, and a shelf-life extension
updating two of them.

DATA NOTE -- NOTHING IS MIGRATED INTO THIS TABLE, and there is nothing to
migrate. No existing column anywhere holds a therapeutic indication, a
posology or a contraindication; before this table the platform could not
represent them at all, which is why leaves 1.3.1-1.3.3 were blocked. Every
existing project therefore reports R30 ("no product information has been
entered") until its SmPC content is filled in, which is an accurate
statement about a dossier with no SmPC in it.

WHY the three list columns are JSON and not child tables: they are always
read and written as a whole -- an SmPC section is edited as a unit -- and
nothing else in the dossier points at an individual entry. Same call, same
reasoning, as `project.condition_answers` in the P17 migration. The day a
side effect has to be linked to the pharmacovigilance signal that found
it, an entry needs an identity and it earns a table.

WHY `product_id` is UNIQUE rather than just a foreign key: "the three
documents read one row" has to be a database fact, not a convention the
application maintains. A second row for the same product is the shape of
the defect, so it is unrepresentable.

Revision ID: d4a71c6b8e93
Revises: c9e4a2b71d38
Create Date: 2026-09-08 09:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "d4a71c6b8e93"
down_revision: Union[str, Sequence[str], None] = "c9e4a2b71d38"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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
    op.create_table(
        "product_information",
        *_base_columns(),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        # --- SmPC 4. Clinical particulars ---
        sa.Column("therapeutic_indications", sa.Text(), nullable=True),
        sa.Column("posology_and_administration", sa.Text(), nullable=True),
        sa.Column("contraindications", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("special_warnings", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("interactions", sa.Text(), nullable=True),
        sa.Column("pregnancy_and_lactation", sa.Text(), nullable=True),
        sa.Column("effects_on_driving", sa.Text(), nullable=True),
        sa.Column("undesirable_effects", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("overdose", sa.Text(), nullable=True),
        # --- SmPC 6. Pharmaceutical particulars (the two that are authored) ---
        sa.Column("incompatibilities", sa.Text(), nullable=True),
        sa.Column("special_precautions_for_disposal", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id"),
    )


def downgrade() -> None:
    op.drop_table("product_information")
