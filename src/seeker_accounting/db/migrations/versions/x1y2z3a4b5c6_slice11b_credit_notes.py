"""Slice 11b: Sales and Purchase Credit Notes tables

Revision ID: x1y2z3a4b5c6
Revises: w0x1y2z3a4b5
Create Date: 2025-01-01 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "x1y2z3a4b5c6"
down_revision = "w0x1y2z3a4b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # sales_credit_notes                                                   #
    # ------------------------------------------------------------------ #
    op.create_table(
        "sales_credit_notes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("credit_number", sa.String(40), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("credit_date", sa.Date(), nullable=False),
        sa.Column("currency_code", sa.String(10), nullable=False),
        sa.Column("exchange_rate", sa.Numeric(18, 6), nullable=True),
        sa.Column("status_code", sa.String(20), nullable=False),
        sa.Column("reason_text", sa.Text(), nullable=True),
        sa.Column("reference_number", sa.String(120), nullable=True),
        sa.Column("subtotal_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("tax_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("source_invoice_id", sa.Integer(), nullable=True),
        sa.Column("posted_journal_entry_id", sa.Integer(), nullable=True),
        sa.Column("posted_at", sa.DateTime(), nullable=True),
        sa.Column("posted_by_user_id", sa.Integer(), nullable=True),
        sa.Column("contract_id", sa.Integer(), nullable=True),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["currency_code"], ["currencies.code"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_invoice_id"], ["sales_invoices.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["posted_journal_entry_id"], ["journal_entries.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["posted_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "credit_number", name="uq_scn_company_number"),
    )
    op.create_index("ix_sales_credit_notes_company_id", "sales_credit_notes", ["company_id"])
    op.create_index(
        "ix_sales_credit_notes_company_customer_date",
        "sales_credit_notes",
        ["company_id", "customer_id", "credit_date"],
    )
    op.create_index(
        "ix_sales_credit_notes_company_status",
        "sales_credit_notes",
        ["company_id", "status_code"],
    )

    # ------------------------------------------------------------------ #
    # sales_credit_note_lines                                              #
    # ------------------------------------------------------------------ #
    op.create_table(
        "sales_credit_note_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sales_credit_note_id", sa.Integer(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 2), nullable=False),
        sa.Column("discount_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("discount_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("tax_code_id", sa.Integer(), nullable=True),
        sa.Column("revenue_account_id", sa.Integer(), nullable=False),
        sa.Column("line_subtotal_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("line_tax_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("line_total_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("contract_id", sa.Integer(), nullable=True),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("project_job_id", sa.Integer(), nullable=True),
        sa.Column("project_cost_code_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["sales_credit_note_id"], ["sales_credit_notes.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["revenue_account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sales_credit_note_id", "line_number", name="uq_scnl_cn_line"
        ),
    )
    op.create_index(
        "ix_sales_credit_note_lines_cn_id",
        "sales_credit_note_lines",
        ["sales_credit_note_id"],
    )

    # ------------------------------------------------------------------ #
    # purchase_credit_notes                                                #
    # ------------------------------------------------------------------ #
    op.create_table(
        "purchase_credit_notes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("credit_number", sa.String(40), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("credit_date", sa.Date(), nullable=False),
        sa.Column("currency_code", sa.String(10), nullable=False),
        sa.Column("exchange_rate", sa.Numeric(18, 6), nullable=True),
        sa.Column("status_code", sa.String(20), nullable=False),
        sa.Column("reason_text", sa.Text(), nullable=True),
        sa.Column("supplier_credit_reference", sa.String(120), nullable=True),
        sa.Column("subtotal_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("tax_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("source_bill_id", sa.Integer(), nullable=True),
        sa.Column("posted_journal_entry_id", sa.Integer(), nullable=True),
        sa.Column("posted_at", sa.DateTime(), nullable=True),
        sa.Column("posted_by_user_id", sa.Integer(), nullable=True),
        sa.Column("contract_id", sa.Integer(), nullable=True),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["currency_code"], ["currencies.code"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_bill_id"], ["purchase_bills.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["posted_journal_entry_id"], ["journal_entries.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["posted_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "credit_number", name="uq_pcn_company_number"),
    )
    op.create_index("ix_purchase_credit_notes_company_id", "purchase_credit_notes", ["company_id"])
    op.create_index(
        "ix_purchase_credit_notes_company_supplier_date",
        "purchase_credit_notes",
        ["company_id", "supplier_id", "credit_date"],
    )
    op.create_index(
        "ix_purchase_credit_notes_company_status",
        "purchase_credit_notes",
        ["company_id", "status_code"],
    )

    # ------------------------------------------------------------------ #
    # purchase_credit_note_lines                                           #
    # ------------------------------------------------------------------ #
    op.create_table(
        "purchase_credit_note_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("purchase_credit_note_id", sa.Integer(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=True),
        sa.Column("unit_cost", sa.Numeric(18, 2), nullable=True),
        sa.Column("tax_code_id", sa.Integer(), nullable=True),
        sa.Column("expense_account_id", sa.Integer(), nullable=True),
        sa.Column("line_subtotal_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("line_tax_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("line_total_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("contract_id", sa.Integer(), nullable=True),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("project_job_id", sa.Integer(), nullable=True),
        sa.Column("project_cost_code_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["purchase_credit_note_id"], ["purchase_credit_notes.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["expense_account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "purchase_credit_note_id", "line_number", name="uq_pcnl_cn_line"
        ),
    )
    op.create_index(
        "ix_purchase_credit_note_lines_cn_id",
        "purchase_credit_note_lines",
        ["purchase_credit_note_id"],
    )


def downgrade() -> None:
    op.drop_table("purchase_credit_note_lines")
    op.drop_table("purchase_credit_notes")
    op.drop_table("sales_credit_note_lines")
    op.drop_table("sales_credit_notes")
