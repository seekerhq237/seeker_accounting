"""Slice T4: tax obligations, returns, return lines, and payments.

Adds the operational backbone for tax compliance workflow:

  * ``tax_obligations`` — one row per (company, tax_type, period)
  * ``tax_returns``     — one filing per obligation (status, totals,
    OTP/external references)
  * ``tax_return_lines``— statutory box breakdown for each return
  * ``tax_payments``    — money settling a return (journal link
    optional for Phase 2)

See ``docs/taxation_implementation_blueprint.md`` Phase 1/2.

Revision ID: f0123456789a
Revises: e9fab0123456
Create Date: 2026-04-28 14:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f0123456789a"
down_revision: Union[str, None] = "e9fab0123456"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tax_obligations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("tax_type_code", sa.String(length=50), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column(
            "status_code",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'OPEN'"),
        ),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tax_obligations_company_id", "tax_obligations", ["company_id"])
    op.create_index(
        "ix_tax_obligations_company_period",
        "tax_obligations",
        ["company_id", "tax_type_code", "period_start", "period_end"],
        unique=True,
    )

    op.create_table(
        "tax_returns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("obligation_id", sa.Integer(), nullable=False),
        sa.Column("tax_type_code", sa.String(length=50), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column(
            "status_code",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'DRAFT'"),
        ),
        sa.Column(
            "total_due_amount",
            sa.Numeric(18, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "total_paid_amount",
            sa.Numeric(18, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("filed_at", sa.DateTime(), nullable=True),
        sa.Column("otp_reference", sa.String(length=120), nullable=True),
        sa.Column("external_reference", sa.String(length=120), nullable=True),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column("prepared_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["obligation_id"], ["tax_obligations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["prepared_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tax_returns_company_id", "tax_returns", ["company_id"])
    op.create_index("ix_tax_returns_obligation_id", "tax_returns", ["obligation_id"])

    op.create_table(
        "tax_return_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tax_return_id", sa.Integer(), nullable=False),
        sa.Column("box_code", sa.String(length=80), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column(
            "sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tax_return_id"], ["tax_returns.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tax_return_lines_return_id", "tax_return_lines", ["tax_return_id"]
    )

    op.create_table(
        "tax_payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("tax_return_id", sa.Integer(), nullable=True),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("payment_method_code", sa.String(length=50), nullable=False),
        sa.Column("reference", sa.String(length=120), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("journal_entry_id", sa.Integer(), nullable=True),
        sa.Column("recorded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["tax_return_id"], ["tax_returns.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["journal_entry_id"], ["journal_entries.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tax_payments_company_id", "tax_payments", ["company_id"])
    op.create_index("ix_tax_payments_return_id", "tax_payments", ["tax_return_id"])


def downgrade() -> None:
    op.drop_index("ix_tax_payments_return_id", table_name="tax_payments")
    op.drop_index("ix_tax_payments_company_id", table_name="tax_payments")
    op.drop_table("tax_payments")

    op.drop_index("ix_tax_return_lines_return_id", table_name="tax_return_lines")
    op.drop_table("tax_return_lines")

    op.drop_index("ix_tax_returns_obligation_id", table_name="tax_returns")
    op.drop_index("ix_tax_returns_company_id", table_name="tax_returns")
    op.drop_table("tax_returns")

    op.drop_index("ix_tax_obligations_company_period", table_name="tax_obligations")
    op.drop_index("ix_tax_obligations_company_id", table_name="tax_obligations")
    op.drop_table("tax_obligations")
