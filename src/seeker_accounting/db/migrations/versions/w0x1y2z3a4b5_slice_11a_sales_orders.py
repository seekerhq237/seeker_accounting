"""Slice 11a — Sales orders.

Creates ``sales_orders`` and ``sales_order_lines`` tables and adds a nullable
``source_order_id`` FK on ``sales_invoices`` so invoices created from a
converted order can be traced back.

Revision ID: w0x1y2z3a4b5
Revises: v9w0x1y2z3a4
Create Date: 2026-04-21 12:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "w0x1y2z3a4b5"
down_revision: Union[str, None] = "v9w0x1y2z3a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sales_orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("order_number", sa.String(length=40), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("order_date", sa.Date(), nullable=False),
        sa.Column("requested_delivery_date", sa.Date(), nullable=True),
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
        sa.Column("source_quote_id", sa.Integer(), nullable=True),
        sa.Column("converted_to_invoice_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["currency_code"], ["currencies.code"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_quote_id"], ["customer_quotes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["converted_to_invoice_id"], ["sales_invoices.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "order_number"),
    )
    op.create_index("ix_sales_orders_company_id", "sales_orders", ["company_id"])
    op.create_index(
        "ix_sales_orders_company_id_customer_id_order_date",
        "sales_orders",
        ["company_id", "customer_id", "order_date"],
    )
    op.create_index(
        "ix_sales_orders_company_id_status_code",
        "sales_orders",
        ["company_id", "status_code"],
    )

    op.create_table(
        "sales_order_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sales_order_id", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(["sales_order_id"], ["sales_orders.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tax_code_id"], ["tax_codes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["revenue_account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_job_id"], ["project_jobs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_cost_code_id"], ["project_cost_codes.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sales_order_id", "line_number"),
    )
    op.create_index("ix_sales_order_lines_project_id", "sales_order_lines", ["project_id"])
    op.create_index("ix_sales_order_lines_project_job_id", "sales_order_lines", ["project_job_id"])

    # Add source_order_id to sales_invoices so converted invoices reference back to the order.
    with op.batch_alter_table("sales_invoices") as batch_op:
        batch_op.add_column(
            sa.Column(
                "source_order_id",
                sa.Integer(),
                sa.ForeignKey("sales_orders.id", ondelete="RESTRICT"),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("sales_invoices") as batch_op:
        batch_op.drop_column("source_order_id")
    op.drop_index("ix_sales_order_lines_project_job_id", table_name="sales_order_lines")
    op.drop_index("ix_sales_order_lines_project_id", table_name="sales_order_lines")
    op.drop_table("sales_order_lines")
    op.drop_index("ix_sales_orders_company_id_status_code", table_name="sales_orders")
    op.drop_index("ix_sales_orders_company_id_customer_id_order_date", table_name="sales_orders")
    op.drop_index("ix_sales_orders_company_id", table_name="sales_orders")
    op.drop_table("sales_orders")
