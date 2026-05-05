"""T44: add multi-currency VAT columns to posted_tax_lines.

Adds base_amount, taxable_base_reporting_currency,
tax_amount_reporting_currency, exchange_rate, rate_source, and
transaction_currency_code to posted_tax_lines.  All are nullable for
backward compatibility with pre-T44 rows.

Revision ID: a14b00000021
Revises: a14b00000020
Create Date: 2025-01-01 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "a14b00000021"
down_revision = "a14b00000020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "posted_tax_lines",
        sa.Column("base_amount", sa.Numeric(18, 2), nullable=True),
    )
    op.add_column(
        "posted_tax_lines",
        sa.Column(
            "taxable_base_reporting_currency", sa.Numeric(18, 2), nullable=True
        ),
    )
    op.add_column(
        "posted_tax_lines",
        sa.Column(
            "tax_amount_reporting_currency", sa.Numeric(18, 2), nullable=True
        ),
    )
    op.add_column(
        "posted_tax_lines",
        sa.Column("exchange_rate", sa.Numeric(18, 6), nullable=True),
    )
    op.add_column(
        "posted_tax_lines",
        sa.Column("rate_source", sa.String(50), nullable=True),
    )
    op.add_column(
        "posted_tax_lines",
        sa.Column("transaction_currency_code", sa.String(3), nullable=True),
    )


def downgrade() -> None:
    # SQLite does not support DROP COLUMN natively (pre-3.35).
    # Alembic's batch mode would require recreating the table; for now
    # we leave downgrade as a no-op and rely on migration history.
    pass
