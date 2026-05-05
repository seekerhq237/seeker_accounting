"""Add payroll run reversal columns.

Revision ID: a14b00000005
Revises: a14b00000004
Create Date: 2026-04-29

Audit finding (Reversal workflow): a posted payroll run had no controlled
way to be reversed in the GL. Voiding raised an error against posted runs,
so accounting corrections required manual journal entries outside the
payroll service contract.

This migration adds tracking columns on ``payroll_runs`` so the reversal
service can:

    - Persist the ``reversed_at`` / ``reversed_by_user_id`` audit pair.
    - Link the offsetting ``reversal_journal_entry_id`` to the run.
    - Capture an operator ``reversal_reason``.

The new ``reversed`` value of ``status_code`` is enforced at service level;
no DB enum change is required.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# Alembic identifiers
revision = "a14b00000005"
down_revision = "a14b00000004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("payroll_runs") as batch:
        batch.add_column(sa.Column("reversed_at", sa.DateTime(), nullable=True))
        batch.add_column(
            sa.Column(
                "reversed_by_user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="RESTRICT"),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column(
                "reversal_journal_entry_id",
                sa.Integer(),
                sa.ForeignKey("journal_entries.id", ondelete="RESTRICT"),
                nullable=True,
            )
        )
        batch.add_column(sa.Column("reversal_reason", sa.String(500), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("payroll_runs") as batch:
        batch.drop_column("reversal_reason")
        batch.drop_column("reversal_journal_entry_id")
        batch.drop_column("reversed_by_user_id")
        batch.drop_column("reversed_at")
