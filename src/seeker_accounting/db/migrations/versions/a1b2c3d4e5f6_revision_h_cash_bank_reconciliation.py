"""revision_h_cash_bank_reconciliation

Revision ID: a1b2c3d4e5f6
Revises: 9d0e1f2a3b4c
Create Date: 2026-03-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "9d0e1f2a3b4c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- treasury_transactions ---
    op.create_table(
        "treasury_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("transaction_number", sa.String(40), nullable=False),
        sa.Column("transaction_type_code", sa.String(30), nullable=False),
        sa.Column("financial_account_id", sa.Integer(), sa.ForeignKey("financial_accounts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("currency_code", sa.String(3), sa.ForeignKey("currencies.code", ondelete="RESTRICT"), nullable=False),
        sa.Column("exchange_rate", sa.Numeric(18, 6), nullable=True),
        sa.Column("total_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("status_code", sa.String(20), nullable=False),
        sa.Column("reference_number", sa.String(120), nullable=True),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("posted_journal_entry_id", sa.Integer(), sa.ForeignKey("journal_entries.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("posted_at", sa.DateTime(), nullable=True),
        sa.Column("posted_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "transaction_number"),
    )
    op.create_index("ix_treasury_transactions_company_id", "treasury_transactions", ["company_id"])
    op.create_index("ix_treasury_transactions_company_id_status_code", "treasury_transactions", ["company_id", "status_code"])
    op.create_index("ix_treasury_transactions_company_id_transaction_type_code", "treasury_transactions", ["company_id", "transaction_type_code"])
    op.create_index(
        "ix_treasury_transactions_company_id_financial_account_id_transaction_date",
        "treasury_transactions",
        ["company_id", "financial_account_id", "transaction_date"],
    )

    # --- treasury_transaction_lines ---
    op.create_table(
        "treasury_transaction_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("treasury_transaction_id", sa.Integer(), sa.ForeignKey("treasury_transactions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("line_description", sa.String(255), nullable=True),
        sa.Column("party_type", sa.String(30), nullable=True),
        sa.Column("party_id", sa.Integer(), nullable=True),
        sa.Column("tax_code_id", sa.Integer(), sa.ForeignKey("tax_codes.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("treasury_transaction_id", "line_number"),
    )

    # --- treasury_transfers ---
    op.create_table(
        "treasury_transfers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("transfer_number", sa.String(40), nullable=False),
        sa.Column("from_financial_account_id", sa.Integer(), sa.ForeignKey("financial_accounts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("to_financial_account_id", sa.Integer(), sa.ForeignKey("financial_accounts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("transfer_date", sa.Date(), nullable=False),
        sa.Column("currency_code", sa.String(3), sa.ForeignKey("currencies.code", ondelete="RESTRICT"), nullable=False),
        sa.Column("exchange_rate", sa.Numeric(18, 6), nullable=True),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("status_code", sa.String(20), nullable=False),
        sa.Column("reference_number", sa.String(120), nullable=True),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("posted_journal_entry_id", sa.Integer(), sa.ForeignKey("journal_entries.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("posted_at", sa.DateTime(), nullable=True),
        sa.Column("posted_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "transfer_number"),
    )
    op.create_index("ix_treasury_transfers_company_id", "treasury_transfers", ["company_id"])
    op.create_index("ix_treasury_transfers_company_id_status_code", "treasury_transfers", ["company_id", "status_code"])
    op.create_index("ix_treasury_transfers_company_id_transfer_date", "treasury_transfers", ["company_id", "transfer_date"])

    # --- bank_statement_import_batches ---
    op.create_table(
        "bank_statement_import_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("financial_account_id", sa.Integer(), sa.ForeignKey("financial_accounts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=True),
        sa.Column("import_source", sa.String(30), nullable=False),
        sa.Column("statement_start_date", sa.Date(), nullable=True),
        sa.Column("statement_end_date", sa.Date(), nullable=True),
        sa.Column("line_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("imported_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("imported_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
    )
    op.create_index("ix_bank_statement_import_batches_company_id", "bank_statement_import_batches", ["company_id"])
    op.create_index(
        "ix_bank_statement_import_batches_company_id_financial_account_id",
        "bank_statement_import_batches",
        ["company_id", "financial_account_id"],
    )

    # --- bank_statement_lines ---
    op.create_table(
        "bank_statement_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("financial_account_id", sa.Integer(), sa.ForeignKey("financial_accounts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("import_batch_id", sa.Integer(), sa.ForeignKey("bank_statement_import_batches.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("line_date", sa.Date(), nullable=False),
        sa.Column("value_date", sa.Date(), nullable=True),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("reference", sa.String(120), nullable=True),
        sa.Column("debit_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("credit_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("is_reconciled", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_bank_statement_lines_company_id", "bank_statement_lines", ["company_id"])
    op.create_index(
        "ix_bank_statement_lines_company_id_financial_account_id",
        "bank_statement_lines",
        ["company_id", "financial_account_id"],
    )
    op.create_index(
        "ix_bank_statement_lines_company_id_is_reconciled",
        "bank_statement_lines",
        ["company_id", "is_reconciled"],
    )

    # --- bank_reconciliation_sessions ---
    op.create_table(
        "bank_reconciliation_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("financial_account_id", sa.Integer(), sa.ForeignKey("financial_accounts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("statement_end_date", sa.Date(), nullable=False),
        sa.Column("statement_ending_balance", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("status_code", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("completed_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
    )
    op.create_index("ix_bank_reconciliation_sessions_company_id", "bank_reconciliation_sessions", ["company_id"])
    op.create_index(
        "ix_bank_reconciliation_sessions_company_id_financial_account_id",
        "bank_reconciliation_sessions",
        ["company_id", "financial_account_id"],
    )

    # --- bank_reconciliation_matches ---
    op.create_table(
        "bank_reconciliation_matches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("reconciliation_session_id", sa.Integer(), sa.ForeignKey("bank_reconciliation_sessions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("bank_statement_line_id", sa.Integer(), sa.ForeignKey("bank_statement_lines.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("match_entity_type", sa.String(50), nullable=False),
        sa.Column("match_entity_id", sa.Integer(), nullable=False),
        sa.Column("matched_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "reconciliation_session_id",
            "bank_statement_line_id",
            "match_entity_type",
            "match_entity_id",
        ),
    )
    op.create_index("ix_bank_reconciliation_matches_session_id", "bank_reconciliation_matches", ["reconciliation_session_id"])
    op.create_index("ix_bank_reconciliation_matches_statement_line_id", "bank_reconciliation_matches", ["bank_statement_line_id"])


def downgrade() -> None:
    op.drop_table("bank_reconciliation_matches")
    op.drop_table("bank_reconciliation_sessions")
    op.drop_table("bank_statement_lines")
    op.drop_table("bank_statement_import_batches")
    op.drop_table("treasury_transfers")
    op.drop_table("treasury_transaction_lines")
    op.drop_table("treasury_transactions")
