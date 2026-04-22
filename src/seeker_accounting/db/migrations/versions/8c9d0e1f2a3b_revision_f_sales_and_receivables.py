"""revision_f_sales_and_receivables

Revision ID: 8c9d0e1f2a3b
Revises: 7b8c9d0e1f2a
Create Date: 2026-03-24 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "8c9d0e1f2a3b"
down_revision = "7b8c9d0e1f2a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- financial_accounts ---
    op.create_table(
        "financial_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("account_code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("financial_account_type_code", sa.String(length=30), nullable=False),
        sa.Column("gl_account_id", sa.Integer(), nullable=False),
        sa.Column("bank_name", sa.String(length=255), nullable=True),
        sa.Column("bank_account_number", sa.String(length=100), nullable=True),
        sa.Column("bank_branch", sa.String(length=120), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_financial_accounts_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["gl_account_id"],
            ["accounts.id"],
            name=op.f("fk_financial_accounts_gl_account_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["currency_code"],
            ["currencies.code"],
            name=op.f("fk_financial_accounts_currency_code_currencies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_financial_accounts")),
        sa.UniqueConstraint(
            "company_id", "account_code", name=op.f("uq_financial_accounts_company_id_account_code")
        ),
    )
    op.create_index("ix_financial_accounts_company_id", "financial_accounts", ["company_id"], unique=False)

    # --- sales_invoices ---
    op.create_table(
        "sales_invoices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("invoice_number", sa.String(length=40), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("exchange_rate", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("status_code", sa.String(length=20), nullable=False),
        sa.Column("payment_status_code", sa.String(length=20), nullable=False),
        sa.Column("reference_number", sa.String(length=120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("subtotal_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("tax_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("total_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("posted_journal_entry_id", sa.Integer(), nullable=True),
        sa.Column("posted_at", sa.DateTime(), nullable=True),
        sa.Column("posted_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_sales_invoices_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_sales_invoices_customer_id_customers"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["currency_code"],
            ["currencies.code"],
            name=op.f("fk_sales_invoices_currency_code_currencies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["posted_journal_entry_id"],
            ["journal_entries.id"],
            name=op.f("fk_sales_invoices_posted_journal_entry_id_journal_entries"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["posted_by_user_id"],
            ["users.id"],
            name=op.f("fk_sales_invoices_posted_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sales_invoices")),
        sa.UniqueConstraint(
            "company_id", "invoice_number", name=op.f("uq_sales_invoices_company_id_invoice_number")
        ),
    )
    op.create_index("ix_sales_invoices_company_id", "sales_invoices", ["company_id"], unique=False)
    op.create_index(
        "ix_sales_invoices_company_id_status_code",
        "sales_invoices",
        ["company_id", "status_code"],
        unique=False,
    )
    op.create_index(
        "ix_sales_invoices_company_id_customer_id",
        "sales_invoices",
        ["company_id", "customer_id"],
        unique=False,
    )

    # --- sales_invoice_lines ---
    op.create_table(
        "sales_invoice_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sales_invoice_id", sa.Integer(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("discount_percent", sa.Numeric(precision=9, scale=4), nullable=True),
        sa.Column("discount_amount", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("tax_code_id", sa.Integer(), nullable=True),
        sa.Column("revenue_account_id", sa.Integer(), nullable=False),
        sa.Column("line_subtotal_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("line_tax_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("line_total_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["sales_invoice_id"],
            ["sales_invoices.id"],
            name=op.f("fk_sales_invoice_lines_sales_invoice_id_sales_invoices"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tax_code_id"],
            ["tax_codes.id"],
            name=op.f("fk_sales_invoice_lines_tax_code_id_tax_codes"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["revenue_account_id"],
            ["accounts.id"],
            name=op.f("fk_sales_invoice_lines_revenue_account_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sales_invoice_lines")),
        sa.UniqueConstraint(
            "sales_invoice_id", "line_number",
            name=op.f("uq_sales_invoice_lines_sales_invoice_id_line_number"),
        ),
    )

    # --- customer_receipts ---
    op.create_table(
        "customer_receipts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("receipt_number", sa.String(length=40), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("financial_account_id", sa.Integer(), nullable=False),
        sa.Column("receipt_date", sa.Date(), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("exchange_rate", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("amount_received", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("status_code", sa.String(length=20), nullable=False),
        sa.Column("reference_number", sa.String(length=120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("posted_journal_entry_id", sa.Integer(), nullable=True),
        sa.Column("posted_at", sa.DateTime(), nullable=True),
        sa.Column("posted_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_customer_receipts_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_customer_receipts_customer_id_customers"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["financial_account_id"],
            ["financial_accounts.id"],
            name=op.f("fk_customer_receipts_financial_account_id_financial_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["currency_code"],
            ["currencies.code"],
            name=op.f("fk_customer_receipts_currency_code_currencies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["posted_journal_entry_id"],
            ["journal_entries.id"],
            name=op.f("fk_customer_receipts_posted_journal_entry_id_journal_entries"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["posted_by_user_id"],
            ["users.id"],
            name=op.f("fk_customer_receipts_posted_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customer_receipts")),
        sa.UniqueConstraint(
            "company_id", "receipt_number",
            name=op.f("uq_customer_receipts_company_id_receipt_number"),
        ),
    )
    op.create_index("ix_customer_receipts_company_id", "customer_receipts", ["company_id"], unique=False)
    op.create_index(
        "ix_customer_receipts_company_id_status_code",
        "customer_receipts",
        ["company_id", "status_code"],
        unique=False,
    )
    op.create_index(
        "ix_customer_receipts_company_id_customer_id",
        "customer_receipts",
        ["company_id", "customer_id"],
        unique=False,
    )

    # --- customer_receipt_allocations ---
    op.create_table(
        "customer_receipt_allocations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("customer_receipt_id", sa.Integer(), nullable=False),
        sa.Column("sales_invoice_id", sa.Integer(), nullable=False),
        sa.Column("allocated_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("allocation_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_customer_receipt_allocations_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["customer_receipt_id"],
            ["customer_receipts.id"],
            name=op.f("fk_customer_receipt_allocations_customer_receipt_id_customer_receipts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["sales_invoice_id"],
            ["sales_invoices.id"],
            name=op.f("fk_customer_receipt_allocations_sales_invoice_id_sales_invoices"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customer_receipt_allocations")),
        sa.UniqueConstraint(
            "customer_receipt_id", "sales_invoice_id",
            name=op.f("uq_customer_receipt_allocations_customer_receipt_id_sales_invoice_id"),
        ),
    )
    op.create_index(
        "ix_customer_receipt_allocations_sales_invoice_id",
        "customer_receipt_allocations",
        ["sales_invoice_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_customer_receipt_allocations_sales_invoice_id", table_name="customer_receipt_allocations")
    op.drop_table("customer_receipt_allocations")
    op.drop_index("ix_customer_receipts_company_id_customer_id", table_name="customer_receipts")
    op.drop_index("ix_customer_receipts_company_id_status_code", table_name="customer_receipts")
    op.drop_index("ix_customer_receipts_company_id", table_name="customer_receipts")
    op.drop_table("customer_receipts")
    op.drop_table("sales_invoice_lines")
    op.drop_index("ix_sales_invoices_company_id_customer_id", table_name="sales_invoices")
    op.drop_index("ix_sales_invoices_company_id_status_code", table_name="sales_invoices")
    op.drop_index("ix_sales_invoices_company_id", table_name="sales_invoices")
    op.drop_table("sales_invoices")
    op.drop_index("ix_financial_accounts_company_id", table_name="financial_accounts")
    op.drop_table("financial_accounts")
