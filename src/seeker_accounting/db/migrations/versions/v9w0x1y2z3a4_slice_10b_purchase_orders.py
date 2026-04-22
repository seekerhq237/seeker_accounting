"""Slice 10b — Purchase orders.

Creates ``purchase_orders`` and ``purchase_order_lines`` tables and adds
a nullable ``source_order_id`` FK on ``purchase_bills`` so bills created
from a converted order can be traced back.

Revision ID: v9w0x1y2z3a4
Revises: u8v9w0x1y2z3
Create Date: 2026-04-21 10:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "v9w0x1y2z3a4"
down_revision: Union[str, None] = "u8v9w0x1y2z3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "purchase_orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("order_number", sa.String(length=40), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("order_date", sa.Date(), nullable=False),
        sa.Column("expected_delivery_date", sa.Date(), nullable=True),
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
        sa.Column("converted_to_bill_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["currency_code"], ["currencies.code"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["converted_to_bill_id"], ["purchase_bills.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "order_number"),
    )
    op.create_index("ix_purchase_orders_company_id", "purchase_orders", ["company_id"])
    op.create_index(
        "ix_purchase_orders_company_id_supplier_id_order_date",
        "purchase_orders",
        ["company_id", "supplier_id", "order_date"],
    )
    op.create_index(
        "ix_purchase_orders_company_id_status_code",
        "purchase_orders",
        ["company_id", "status_code"],
    )

    op.create_table(
        "purchase_order_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("purchase_order_id", sa.Integer(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("unit_cost", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("discount_percent", sa.Numeric(precision=9, scale=4), nullable=True),
        sa.Column("discount_amount", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("tax_code_id", sa.Integer(), nullable=True),
        sa.Column("expense_account_id", sa.Integer(), nullable=True),
        sa.Column("line_subtotal_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("line_tax_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("line_total_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("contract_id", sa.Integer(), nullable=True),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("project_job_id", sa.Integer(), nullable=True),
        sa.Column("project_cost_code_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["purchase_order_id"], ["purchase_orders.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["tax_code_id"], ["tax_codes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["expense_account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_job_id"], ["project_jobs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["project_cost_code_id"], ["project_cost_codes.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("purchase_order_id", "line_number"),
    )
    op.create_index(
        "ix_purchase_order_lines_project_id", "purchase_order_lines", ["project_id"]
    )
    op.create_index(
        "ix_purchase_order_lines_project_job_id", "purchase_order_lines", ["project_job_id"]
    )

    # Add source_order_id FK to purchase_bills so a bill can trace back its origin order.
    op.add_column(
        "purchase_bills",
        sa.Column("source_order_id", sa.Integer(), nullable=True),
    )
    with op.batch_alter_table("purchase_bills") as batch_op:
        batch_op.create_foreign_key(
            "fk_purchase_bills_source_order_id",
            "purchase_orders",
            ["source_order_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    with op.batch_alter_table("purchase_bills") as batch_op:
        batch_op.drop_constraint("fk_purchase_bills_source_order_id", type_="foreignkey")
    op.drop_column("purchase_bills", "source_order_id")

    op.drop_index("ix_purchase_order_lines_project_job_id", table_name="purchase_order_lines")
    op.drop_index("ix_purchase_order_lines_project_id", table_name="purchase_order_lines")
    op.drop_table("purchase_order_lines")

    op.drop_index("ix_purchase_orders_company_id_status_code", table_name="purchase_orders")
    op.drop_index(
        "ix_purchase_orders_company_id_supplier_id_order_date", table_name="purchase_orders"
    )
    op.drop_index("ix_purchase_orders_company_id", table_name="purchase_orders")
    op.drop_table("purchase_orders")
