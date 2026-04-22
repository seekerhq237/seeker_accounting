"""revision_g_purchases_and_payables

Revision ID: 9d0e1f2a3b4c
Revises: 8c9d0e1f2a3b
Create Date: 2026-03-24 14:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9d0e1f2a3b4c"
down_revision = "8c9d0e1f2a3b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- purchase_bills ---
    op.create_table(
        "purchase_bills",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("bill_number", sa.String(length=40), nullable=False),
        sa.Column("supplier_bill_reference", sa.String(length=120), nullable=True),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("bill_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("exchange_rate", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("status_code", sa.String(length=20), nullable=False),
        sa.Column("payment_status_code", sa.String(length=20), nullable=False),
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
            name=op.f("fk_purchase_bills_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["suppliers.id"],
            name=op.f("fk_purchase_bills_supplier_id_suppliers"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["currency_code"],
            ["currencies.code"],
            name=op.f("fk_purchase_bills_currency_code_currencies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["posted_journal_entry_id"],
            ["journal_entries.id"],
            name=op.f("fk_purchase_bills_posted_journal_entry_id_journal_entries"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["posted_by_user_id"],
            ["users.id"],
            name=op.f("fk_purchase_bills_posted_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_purchase_bills")),
        sa.UniqueConstraint(
            "company_id", "bill_number", name=op.f("uq_purchase_bills_company_id_bill_number")
        ),
    )
    op.create_index("ix_purchase_bills_company_id", "purchase_bills", ["company_id"], unique=False)
    op.create_index(
        "ix_purchase_bills_company_id_supplier_id_bill_date",
        "purchase_bills",
        ["company_id", "supplier_id", "bill_date"],
        unique=False,
    )
    op.create_index("ix_purchase_bills_company_id_status_code", "purchase_bills", ["company_id", "status_code"], unique=False)
    op.create_index(
        "ix_purchase_bills_company_id_payment_status_code",
        "purchase_bills",
        ["company_id", "payment_status_code"],
        unique=False,
    )

    # --- purchase_bill_lines ---
    op.create_table(
        "purchase_bill_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("purchase_bill_id", sa.Integer(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("unit_cost", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("expense_account_id", sa.Integer(), nullable=True),
        sa.Column("tax_code_id", sa.Integer(), nullable=True),
        sa.Column("line_subtotal_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("line_tax_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("line_total_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["purchase_bill_id"],
            ["purchase_bills.id"],
            name=op.f("fk_purchase_bill_lines_purchase_bill_id_purchase_bills"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["expense_account_id"],
            ["accounts.id"],
            name=op.f("fk_purchase_bill_lines_expense_account_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tax_code_id"],
            ["tax_codes.id"],
            name=op.f("fk_purchase_bill_lines_tax_code_id_tax_codes"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_purchase_bill_lines")),
        sa.UniqueConstraint(
            "purchase_bill_id", "line_number", name=op.f("uq_purchase_bill_lines_purchase_bill_id_line_number")
        ),
    )

    # --- supplier_payments ---
    op.create_table(
        "supplier_payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("payment_number", sa.String(length=40), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("financial_account_id", sa.Integer(), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("exchange_rate", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("amount_paid", sa.Numeric(precision=18, scale=2), nullable=False),
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
            name=op.f("fk_supplier_payments_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["suppliers.id"],
            name=op.f("fk_supplier_payments_supplier_id_suppliers"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["financial_account_id"],
            ["financial_accounts.id"],
            name=op.f("fk_supplier_payments_financial_account_id_financial_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["currency_code"],
            ["currencies.code"],
            name=op.f("fk_supplier_payments_currency_code_currencies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["posted_journal_entry_id"],
            ["journal_entries.id"],
            name=op.f("fk_supplier_payments_posted_journal_entry_id_journal_entries"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["posted_by_user_id"],
            ["users.id"],
            name=op.f("fk_supplier_payments_posted_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_supplier_payments")),
        sa.UniqueConstraint(
            "company_id", "payment_number", name=op.f("uq_supplier_payments_company_id_payment_number")
        ),
    )
    op.create_index("ix_supplier_payments_company_id", "supplier_payments", ["company_id"], unique=False)
    op.create_index(
        "ix_supplier_payments_company_id_supplier_id_payment_date",
        "supplier_payments",
        ["company_id", "supplier_id", "payment_date"],
        unique=False,
    )
    op.create_index("ix_supplier_payments_company_id_status_code", "supplier_payments", ["company_id", "status_code"], unique=False)

    # --- supplier_payment_allocations ---
    op.create_table(
        "supplier_payment_allocations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("supplier_payment_id", sa.Integer(), nullable=False),
        sa.Column("purchase_bill_id", sa.Integer(), nullable=False),
        sa.Column("allocated_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("allocation_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_supplier_payment_allocations_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["supplier_payment_id"],
            ["supplier_payments.id"],
            name=op.f("fk_supplier_payment_allocations_supplier_payment_id_supplier_payments"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["purchase_bill_id"],
            ["purchase_bills.id"],
            name=op.f("fk_supplier_payment_allocations_purchase_bill_id_purchase_bills"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_supplier_payment_allocations")),
        sa.UniqueConstraint(
            "supplier_payment_id",
            "purchase_bill_id",
            name=op.f("uq_supplier_payment_allocations_supplier_payment_id_purchase_bill_id"),
        ),
    )
    op.create_index(
        "ix_supplier_payment_allocations_purchase_bill_id",
        "supplier_payment_allocations",
        ["purchase_bill_id"],
        unique=False,
    )


def downgrade() -> None:
    # --- supplier_payment_allocations ---
    op.drop_index("ix_supplier_payment_allocations_purchase_bill_id", table_name="supplier_payment_allocations")
    op.drop_table("supplier_payment_allocations")

    # --- supplier_payments ---
    op.drop_index("ix_supplier_payments_company_id_status_code", table_name="supplier_payments")
    op.drop_index(
        "ix_supplier_payments_company_id_supplier_id_payment_date",
        table_name="supplier_payments",
    )
    op.drop_index("ix_supplier_payments_company_id", table_name="supplier_payments")
    op.drop_table("supplier_payments")

    # --- purchase_bill_lines ---
    op.drop_table("purchase_bill_lines")

    # --- purchase_bills ---
    op.drop_index("ix_purchase_bills_company_id_payment_status_code", table_name="purchase_bills")
    op.drop_index("ix_purchase_bills_company_id_status_code", table_name="purchase_bills")
    op.drop_index(
        "ix_purchase_bills_company_id_supplier_id_bill_date",
        table_name="purchase_bills",
    )
    op.drop_index("ix_purchase_bills_company_id", table_name="purchase_bills")
    op.drop_table("purchase_bills")
