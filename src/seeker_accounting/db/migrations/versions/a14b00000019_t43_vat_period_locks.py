"""Alembic migration: T43 — vat_period_locks table.

Revision: a14b00000019
Creates the ``vat_period_locks`` table that gates new postings
from backdating into a filed VAT period.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a14b00000019"
down_revision = "a14b00000018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vat_period_locks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("tax_type_code", sa.String(20), nullable=False, server_default="VAT"),
        sa.Column("locked_at", sa.DateTime(), nullable=False),
        sa.Column("locked_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "return_id",
            sa.Integer(),
            sa.ForeignKey("tax_returns.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint(
            "company_id", "period_start", "period_end", "tax_type_code",
            name="uq_vat_period_locks_company_period_type",
        ),
    )
    op.create_index(
        "ix_vat_period_locks_company_id",
        "vat_period_locks",
        ["company_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_vat_period_locks_company_id", table_name="vat_period_locks")
    op.drop_table("vat_period_locks")
