"""T34: company_pro_rata_history table.

Tracks provisional and final VAT pro-rata percentages per fiscal year
for companies using a partial-exemption (mixed) VAT regime.

Revision ID: a14b00000017
Revises: a14b00000016
Create Date: 2026-05-15 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a14b00000017"
down_revision = "a14b00000016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_pro_rata_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("provisional_pct", sa.Numeric(7, 4), nullable=True),
        sa.Column("final_pct", sa.Numeric(7, 4), nullable=True),
        sa.Column(
            "adjustment_journal_entry_id",
            sa.Integer(),
            sa.ForeignKey("journal_entries.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_company_pro_rata_history_company_year",
        "company_pro_rata_history",
        ["company_id", "fiscal_year"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_company_pro_rata_history_company_year",
        table_name="company_pro_rata_history",
    )
    op.drop_table("company_pro_rata_history")
