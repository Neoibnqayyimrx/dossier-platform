"""P25 unique sequence number per project

One constraint, and it closes a race that had been open since P02.

`create_sequence` allocated the next transaction id by reading
`max(number)` and then inserting. Those are two statements, so two
concurrent POSTs to the same project could both read 0002 and both insert
0003. Nothing in the schema refused the second write.

WHY that matters more than an ordinary duplicate row: the sequence number
is the identifier the AGENCY files the submission under. An eCTD lifecycle
operation in 0003 points back at a leaf in 0002 by number, so two rows
sharing 0003 is not a display glitch -- it is a submission history that
cannot be unambiguously read afterwards, because nothing records which of
the two was really 0003. It is also unrepairable by renumbering once the
sequence has been sent: the agency's copy has the number we gave it.

The application-side retry (app/api/routers/projects.py) is the recovery,
not the guarantee. Only the database can refuse the losing write, because
only the database sees both transactions.

DATA NOTE -- existing duplicates are NOT auto-repaired. If a project
already holds two sequences with the same number, this migration fails with
an explicit error listing them rather than picking a winner. Renumbering a
regulatory transaction id is a decision with submission consequences (which
one was filed? was either?), and a migration is the wrong place to guess.
The operator resolves it, then re-runs.

Revision ID: f5c8b21a90d7
Revises: d4a71c6b8e93
Create Date: 2026-09-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f5c8b21a90d7"
down_revision = "d4a71c6b8e93"
branch_labels = None
depends_on = None

CONSTRAINT_NAME = "uq_sequence_project_number"


def upgrade() -> None:
    _assert_no_duplicates()
    # WHY batch_alter_table: SQLite has no ALTER TABLE ADD CONSTRAINT, and
    # tests/test_migration.py runs this migration against SQLite. Batch mode
    # recreates the table there and issues a plain ALTER on Postgres, so one
    # spelling covers both dialects.
    with op.batch_alter_table("sequence") as batch_op:
        batch_op.create_unique_constraint(CONSTRAINT_NAME, ["project_id", "number"])


def downgrade() -> None:
    with op.batch_alter_table("sequence") as batch_op:
        batch_op.drop_constraint(CONSTRAINT_NAME, type_="unique")


def _assert_no_duplicates() -> None:
    """Fail loudly, and say exactly which rows are the problem."""
    bind = op.get_bind()
    duplicates = bind.execute(
        sa.text(
            "SELECT project_id, number, COUNT(*) AS n "
            "FROM sequence GROUP BY project_id, number HAVING COUNT(*) > 1"
        )
    ).all()
    if duplicates:
        listed = ", ".join(
            f"project {row.project_id} number {row.number} (x{row.n})" for row in duplicates
        )
        raise RuntimeError(
            "Cannot add the unique sequence-number constraint: duplicate "
            f"(project_id, number) rows already exist -- {listed}. These are "
            "regulatory transaction ids, so this migration will not choose "
            "which row keeps the number. Decide which sequence was actually "
            "filed under it, renumber or delete the other, then re-run."
        )
