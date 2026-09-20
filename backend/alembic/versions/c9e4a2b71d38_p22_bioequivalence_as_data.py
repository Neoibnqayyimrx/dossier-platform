"""P22 bioequivalence as data

Four new tables and three new columns on `product`, because a
bioequivalence study is the one thing in a multisource dossier that had to
be structured and was not (see app/models/bioequivalence.py):

  reference_product      the comparator, with an identity AND a batch
  bioequivalence_study   design, conduct, and the two cross-references
                         (comparator, test batch) that make it checkable
  bioequivalence_result  one row per PK parameter: the ratio and its 90 % CI
  biowaiver              the other route -- a BCS or additional-strength
                         request, which is what leaves 1.2.17 and 1.2.18
                         are rendered from

On `product`: `reference_product_name` and
`reference_product_manufacturer` (what the APPLICATION declares, printed at
1.2 and 2.3 and reconciled by rule R26 against what each study actually
dosed), and `narrow_therapeutic_index` (which of the region's two
acceptance windows this molecule is judged against).

DATA NOTE 1 -- WHAT IS COPIED. `ClinicalEntry.reference_product` is the
only comparator any existing filing has recorded, and it is COPIED into
`product.reference_product_name` for every product that has one. Nothing
is dropped and nothing is retyped: the filer's comparator survives, and it
lands in the field the registration form now prints.

DATA NOTE 2 -- WHAT IS NOT, AND WHY NOT. A `ClinicalEntry` of kind
"bioequivalence" is NOT converted into a `BioequivalenceStudy`. It cannot
be: the row holds a sentence ("Comparative BA/BE study; bioequivalence
demonstrated"), and a sentence does not contain a study design, a subject
count or a confidence interval. Manufacturing those numbers to fill a
table would be the single worst thing this migration could do -- it would
put invented regulatory data in front of an assessor with the platform's
authority behind it.

So the row stays exactly where it is, and rule R06 stops accepting it as
bioequivalence evidence. Every existing project will report "no
bioequivalence route" until its study is entered, which is an accurate
statement about a dossier whose central document is a paragraph.

WHY no CHECK constraint on `biowaiver.kind` vs `supporting_study_id`: an
additional-strength waiver normally cites the study it leans on and a
BCS-based one does not, but "normally" is not "always" -- a BCS waiver
filed alongside a study at another strength is a real, if unusual, filing.
The rules are the right place for a judgement with exceptions; a CHECK is
for facts that cannot be otherwise.

Revision ID: c9e4a2b71d38
Revises: b3f8c21d90ae
Create Date: 2026-09-07 09:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c9e4a2b71d38"
down_revision: Union[str, Sequence[str], None] = "b3f8c21d90ae"
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
        "reference_product",
        *_base_columns(),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("strength", sa.String(length=120), nullable=True),
        sa.Column("dosage_form", sa.String(length=120), nullable=True),
        sa.Column("manufacturer", sa.String(length=200), nullable=True),
        sa.Column("country_of_origin", sa.String(length=80), nullable=True),
        sa.Column("batch_number", sa.String(length=80), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("purchase_country", sa.String(length=80), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "bioequivalence_study",
        *_base_columns(),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("study_identifier", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=True),
        sa.Column(
            "design",
            sa.Enum("CROSSOVER", "PARALLEL", "REPLICATE_CROSSOVER", name="bestudydesign"),
            nullable=False,
        ),
        sa.Column("fed_state", sa.Enum("FASTING", "FED", name="befedstate"), nullable=False),
        sa.Column(
            "dose_regimen",
            sa.Enum("SINGLE_DOSE", "MULTIPLE_DOSE", name="bedoseregimen"),
            nullable=False,
        ),
        sa.Column("subjects_enrolled", sa.Integer(), nullable=True),
        sa.Column("subjects_completed", sa.Integer(), nullable=True),
        sa.Column("analyte", sa.String(length=200), nullable=True),
        sa.Column("bioanalytical_method", sa.String(length=300), nullable=True),
        sa.Column("cro_name", sa.String(length=200), nullable=True),
        sa.Column("study_site", sa.String(length=300), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("completion_date", sa.Date(), nullable=True),
        sa.Column("reference_product_id", sa.Uuid(), nullable=True),
        sa.Column("test_batch_id", sa.Uuid(), nullable=True),
        sa.Column("test_batch_size_units", sa.Integer(), nullable=True),
        sa.Column("test_batch_manufacture_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"]),
        sa.ForeignKeyConstraint(["reference_product_id"], ["reference_product.id"]),
        sa.ForeignKeyConstraint(["test_batch_id"], ["batch_analysis.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "bioequivalence_result",
        *_base_columns(),
        sa.Column("bioequivalence_study_id", sa.Uuid(), nullable=False),
        sa.Column(
            "parameter",
            sa.Enum("CMAX", "AUC_0_T", "AUC_0_INF", name="pkparameter"),
            nullable=False,
        ),
        # Numeric, not Float, and the precision is not decoration: the
        # acceptance window is written to two decimal places, and a
        # rounding artefact here decides whether a product is approvable.
        sa.Column("geometric_mean_ratio", sa.Numeric(precision=7, scale=2), nullable=True),
        sa.Column("ci_lower", sa.Numeric(precision=7, scale=2), nullable=False),
        sa.Column("ci_upper", sa.Numeric(precision=7, scale=2), nullable=False),
        sa.Column("intra_subject_cv", sa.Numeric(precision=7, scale=2), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["bioequivalence_study_id"], ["bioequivalence_study.id"]),
        sa.PrimaryKeyConstraint("id"),
        # One interval per parameter per study. A second is not extra data,
        # it is a table with two answers in one box -- and whichever the
        # renderer reaches second wins silently. Same call
        # `uq_stability_result_cell` makes one table over.
        sa.UniqueConstraint("bioequivalence_study_id", "parameter", name="uq_be_result_parameter"),
    )

    op.create_table(
        "biowaiver",
        *_base_columns(),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("BCS_BASED", "ADDITIONAL_STRENGTH", name="biowaiverkind"),
            nullable=False,
        ),
        sa.Column("strength", sa.String(length=120), nullable=False),
        sa.Column("bcs_class", sa.Integer(), nullable=True),
        sa.Column("dissolution_similarity_f2", sa.Numeric(precision=7, scale=2), nullable=True),
        sa.Column("supporting_study_id", sa.Uuid(), nullable=True),
        sa.Column("justification", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"]),
        sa.ForeignKeyConstraint(["supporting_study_id"], ["bioequivalence_study.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    with op.batch_alter_table("product") as batch:
        batch.add_column(sa.Column("reference_product_name", sa.String(length=200), nullable=True))
        batch.add_column(
            sa.Column("reference_product_manufacturer", sa.String(length=200), nullable=True)
        )
        batch.add_column(
            sa.Column(
                "narrow_therapeutic_index",
                sa.Boolean(),
                nullable=False,
                server_default="0",
            )
        )

    _carry_the_declared_comparator_across()


def _carry_the_declared_comparator_across() -> None:
    """Copy each product's existing comparator out of `clinical_entry`.

    WHY this is worth the code rather than leaving the column null: the
    comparator is the ONE piece of bioequivalence data an existing filing
    already holds, and it is the field the registration form (1.2) now
    prints. Leaving it null would make every pre-P22 project render
    "[[NOT YET ON FILE]]" on its application form for a fact that is
    sitting in the next table.

    A correlated UPDATE would be shorter, and this is written out because
    the enum is stored by NAME ("BIOEQUIVALENCE", not "bioequivalence") --
    SQLAlchemy's default -- which is exactly the kind of detail a one-line
    UPDATE gets wrong silently, matching nothing and copying nothing while
    reporting success.
    """
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT product_id, reference_product FROM clinical_entry "
            "WHERE kind = 'BIOEQUIVALENCE' AND reference_product IS NOT NULL"
        )
    ).fetchall()

    seen: set[str] = set()
    for product_id, reference_product in rows:
        # First one wins. A product with two bioequivalence rows naming two
        # comparators is a contradiction the old model could hold and this
        # migration cannot resolve -- picking one and letting rule R26
        # report the disagreement against the study is better than picking
        # the last one silently.
        if str(product_id) in seen:
            continue
        seen.add(str(product_id))
        bind.execute(
            sa.text(
                "UPDATE product SET reference_product_name = :name WHERE id = :id "
                "AND reference_product_name IS NULL"
            ),
            {"name": reference_product, "id": product_id},
        )


def downgrade() -> None:
    with op.batch_alter_table("product") as batch:
        batch.drop_column("narrow_therapeutic_index")
        batch.drop_column("reference_product_manufacturer")
        batch.drop_column("reference_product_name")

    op.drop_table("biowaiver")
    op.drop_table("bioequivalence_result")
    op.drop_table("bioequivalence_study")
    op.drop_table("reference_product")
