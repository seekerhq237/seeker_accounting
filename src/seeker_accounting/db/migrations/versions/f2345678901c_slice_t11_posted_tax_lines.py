"""Slice T11: posted tax lines (immutable tax fact table).

Adds the append-only fact table that captures every tax event at the
moment a sales/purchase document (or its credit note) is posted.

Each fact carries a back-link to the journal entry, the source
document, the tax code, the *taxable base* (which the journal entry
cannot represent), the recoverable flag, and the fiscal period. Net
amounts for any period are derived by ``SUM(tax_amount)`` over the
rows in scope — credit notes write **signed-negative** amounts, so a
plain SUM gives the correct net automatically.

See ``docs/taxation_implementation_blueprint.md`` Phase 0 / Slice T11.

Revision ID: f2345678901c
Revises: f1234567890b
Create Date: 2026-05-12 09:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f2345678901c"
down_revision: Union[str, None] = "f1234567890b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "posted_tax_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("fiscal_period_id", sa.Integer(), nullable=False),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("source_document_type", sa.String(length=50), nullable=False),
        sa.Column("source_document_id", sa.Integer(), nullable=False),
        sa.Column("source_line_id", sa.Integer(), nullable=True),
        sa.Column("journal_entry_id", sa.Integer(), nullable=False),
        sa.Column("tax_code_id", sa.Integer(), nullable=True),
        sa.Column("taxable_base", sa.Numeric(18, 2), nullable=False),
        sa.Column("tax_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("is_recoverable", sa.Boolean(), nullable=True),
        sa.Column("posted_at", sa.DateTime(), nullable=False),
        sa.Column("posted_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["fiscal_period_id"], ["fiscal_periods.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["journal_entry_id"], ["journal_entries.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["tax_code_id"], ["tax_codes.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["posted_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_posted_tax_lines_company_id",
        "posted_tax_lines",
        ["company_id"],
    )
    op.create_index(
        "ix_posted_tax_lines_company_period_direction",
        "posted_tax_lines",
        ["company_id", "fiscal_period_id", "direction"],
    )
    op.create_index(
        "ix_posted_tax_lines_source",
        "posted_tax_lines",
        ["company_id", "source_document_type", "source_document_id"],
    )
    op.create_index(
        "ix_posted_tax_lines_company_tax_code",
        "posted_tax_lines",
        ["company_id", "tax_code_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_posted_tax_lines_company_tax_code", table_name="posted_tax_lines"
    )
    op.drop_index("ix_posted_tax_lines_source", table_name="posted_tax_lines")
    op.drop_index(
        "ix_posted_tax_lines_company_period_direction",
        table_name="posted_tax_lines",
    )
    op.drop_index("ix_posted_tax_lines_company_id", table_name="posted_tax_lines")
    op.drop_table("posted_tax_lines")
