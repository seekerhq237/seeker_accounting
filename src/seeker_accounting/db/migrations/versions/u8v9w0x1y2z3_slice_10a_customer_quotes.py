"""Slice 10 (a) — Customer quotes / estimates.

Creates ``customer_quotes`` and ``customer_quote_lines`` tables and adds
a nullable ``source_quote_id`` FK on ``sales_invoices`` so invoices created
from a converted quote can be traced back.

Revision ID: u8v9w0x1y2z3
Revises: t7u8v9w0x1y2
Create Date: 2026-04-10 10:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "u8v9w0x1y2z3"
down_revision: Union[str, None] = "t7u8v9w0x1y2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "customer_quotes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("quote_number", sa.String(length=40), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("quote_date", sa.Date(), nullable=False),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("exchange_rate", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("status_code", sa.String(length=20), nullable=False),
        sa.Column("reference_number", sa.String(length=120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("subtotal_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("tax_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("total_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("contract_id", sa.Integer(), nullable=True),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("converted_to_invoice_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["currency_code"], ["currencies.code"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["converted_to_invoice_id"], ["sales_invoices.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "quote_number"),
    )
    op.create_index("ix_customer_quotes_company_id", "customer_quotes", ["company_id"])
    op.create_index(
        "ix_customer_quotes_company_id_customer_id_quote_date",
        "customer_quotes",
        ["company_id", "customer_id", "quote_date"],
    )
    op.create_index(
        "ix_customer_quotes_company_id_status_code",
        "customer_quotes",
        ["company_id", "status_code"],
    )

    op.create_table(
        "customer_quote_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_quote_id", sa.Integer(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("discount_percent", sa.Numeric(precision=9, scale=4), nullable=True),
        sa.Column("discount_amount", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("tax_code_id", sa.Integer(), nullable=True),
        sa.Column("revenue_account_id", sa.Integer(), nullable=True),
        sa.Column("line_subtotal_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("line_tax_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("line_total_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("contract_id", sa.Integer(), nullable=True),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("project_job_id", sa.Integer(), nullable=True),
        sa.Column("project_cost_code_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["customer_quote_id"], ["customer_quotes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tax_code_id"], ["tax_codes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["revenue_account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_job_id"], ["project_jobs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_cost_code_id"], ["project_cost_codes.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("customer_quote_id", "line_number"),
    )
    op.create_index("ix_customer_quote_lines_project_id", "customer_quote_lines", ["project_id"])
    op.create_index("ix_customer_quote_lines_project_job_id", "customer_quote_lines", ["project_job_id"])

    # sales_invoices.source_quote_id — back-reference for quote-to-invoice conversion.
    with op.batch_alter_table("sales_invoices") as batch_op:
        batch_op.add_column(sa.Column("source_quote_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_sales_invoices_source_quote_id",
            "customer_quotes",
            ["source_quote_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    with op.batch_alter_table("sales_invoices") as batch_op:
        batch_op.drop_constraint("fk_sales_invoices_source_quote_id", type_="foreignkey")
        batch_op.drop_column("source_quote_id")

    op.drop_index("ix_customer_quote_lines_project_job_id", table_name="customer_quote_lines")
    op.drop_index("ix_customer_quote_lines_project_id", table_name="customer_quote_lines")
    op.drop_table("customer_quote_lines")

    op.drop_index("ix_customer_quotes_company_id_status_code", table_name="customer_quotes")
    op.drop_index("ix_customer_quotes_company_id_customer_id_quote_date", table_name="customer_quotes")
    op.drop_index("ix_customer_quotes_company_id", table_name="customer_quotes")
    op.drop_table("customer_quotes")
