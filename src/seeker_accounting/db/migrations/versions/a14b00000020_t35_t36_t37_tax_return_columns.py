"""Compatibility shim for T35/T36/T37 tax return columns.

Revision ID: a14b00000020
Revises: a14b00000019
Create Date: 2026-05-07 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a14b00000020"
down_revision = "a14b00000019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing_columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("tax_returns")
    }
    if "is_amended" not in existing_columns:
        op.add_column(
            "tax_returns",
            sa.Column("is_amended", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "amends_return_id" not in existing_columns:
        op.add_column(
            "tax_returns",
            sa.Column("amends_return_id", sa.Integer(), nullable=True),
        )
    if "credit_brought_forward" not in existing_columns:
        op.add_column(
            "tax_returns",
            sa.Column("credit_brought_forward", sa.Numeric(18, 2), nullable=True),
        )
    if "withholding_vat_amount" not in existing_columns:
        op.add_column(
            "tax_returns",
            sa.Column("withholding_vat_amount", sa.Numeric(18, 2), nullable=True),
        )


def downgrade() -> None:
    # These columns are owned by a14b00000012 in the current migration graph.
    # This duplicate revision remains as an idempotent compatibility shim.
    return
