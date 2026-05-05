"""Alembic migration: T35/T36/T37 — new columns on tax_returns.

Revision: a14b00000020
Adds amendment-tracking, credit-brought-forward, and withholding-VAT
columns to the ``tax_returns`` table.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a14b00000020"
down_revision = "a14b00000019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # T35: amendment support — plain integer, no FK constraint needed for SQLite
    op.add_column(
        "tax_returns",
        sa.Column("is_amended", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "tax_returns",
        sa.Column("amends_return_id", sa.Integer(), nullable=True),
    )
    # T36: credit carried forward from prior period settlement
    op.add_column(
        "tax_returns",
        sa.Column("credit_brought_forward", sa.Numeric(18, 2), nullable=True),
    )
    # T37: withholding VAT deducted at source by the payer
    op.add_column(
        "tax_returns",
        sa.Column("withholding_vat_amount", sa.Numeric(18, 2), nullable=True),
    )


def downgrade() -> None:
    with op.batch_alter_table("tax_returns") as batch_op:
        batch_op.drop_column("withholding_vat_amount")
        batch_op.drop_column("credit_brought_forward")
        batch_op.drop_column("amends_return_id")
        batch_op.drop_column("is_amended")
