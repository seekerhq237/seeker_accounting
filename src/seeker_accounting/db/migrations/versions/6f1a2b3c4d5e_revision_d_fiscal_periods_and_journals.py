"""revision_d_fiscal_periods_and_journals

Revision ID: 6f1a2b3c4d5e
Revises: 9a7b6c5d4e3f
Create Date: 2026-03-24 02:35:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "6f1a2b3c4d5e"
down_revision = "9a7b6c5d4e3f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fiscal_years",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("year_code", sa.String(length=20), nullable=False),
        sa.Column("year_name", sa.String(length=120), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status_code", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_fiscal_years_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fiscal_years")),
        sa.UniqueConstraint("company_id", "year_code", name=op.f("uq_fiscal_years_company_id_year_code")),
        sa.UniqueConstraint(
            "company_id",
            "start_date",
            "end_date",
            name=op.f("uq_fiscal_years_company_id_start_date_end_date"),
        ),
    )

    op.create_table(
        "fiscal_periods",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("fiscal_year_id", sa.Integer(), nullable=False),
        sa.Column("period_number", sa.Integer(), nullable=False),
        sa.Column("period_code", sa.String(length=30), nullable=False),
        sa.Column("period_name", sa.String(length=120), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status_code", sa.String(length=20), nullable=False),
        sa.Column("is_adjustment_period", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("period_number >= 1", name=op.f("ck_fiscal_periods_period_number_positive")),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_fiscal_periods_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["fiscal_year_id"],
            ["fiscal_years.id"],
            name=op.f("fk_fiscal_periods_fiscal_year_id_fiscal_years"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fiscal_periods")),
        sa.UniqueConstraint(
            "company_id",
            "fiscal_year_id",
            "period_number",
            name=op.f("uq_fiscal_periods_company_id_fiscal_year_id_period_number"),
        ),
    )

    op.create_table(
        "journal_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("fiscal_period_id", sa.Integer(), nullable=False),
        sa.Column("entry_number", sa.String(length=40), nullable=True),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("journal_type_code", sa.String(length=30), nullable=False),
        sa.Column("reference_text", sa.String(length=120), nullable=True),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("source_module_code", sa.String(length=50), nullable=True),
        sa.Column("source_document_type", sa.String(length=50), nullable=True),
        sa.Column("source_document_id", sa.Integer(), nullable=True),
        sa.Column("status_code", sa.String(length=20), nullable=False),
        sa.Column("posted_at", sa.DateTime(), nullable=True),
        sa.Column("posted_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_journal_entries_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_journal_entries_created_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["fiscal_period_id"],
            ["fiscal_periods.id"],
            name=op.f("fk_journal_entries_fiscal_period_id_fiscal_periods"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["posted_by_user_id"],
            ["users.id"],
            name=op.f("fk_journal_entries_posted_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_journal_entries")),
        sa.UniqueConstraint("company_id", "entry_number", name=op.f("uq_journal_entries_company_id_entry_number")),
    )
    op.create_index(
        "ix_journal_entries_company_id_entry_date",
        "journal_entries",
        ["company_id", "entry_date"],
        unique=False,
    )
    op.create_index(
        "ix_journal_entries_company_id_status_code",
        "journal_entries",
        ["company_id", "status_code"],
        unique=False,
    )

    op.create_table(
        "journal_entry_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("journal_entry_id", sa.Integer(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("line_description", sa.String(length=255), nullable=True),
        sa.Column("debit_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("credit_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("credit_amount >= 0", name=op.f("ck_journal_entry_lines_credit_amount_non_negative")),
        sa.CheckConstraint("debit_amount >= 0", name=op.f("ck_journal_entry_lines_debit_amount_non_negative")),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_journal_entry_lines_account_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["journal_entry_id"],
            ["journal_entries.id"],
            name=op.f("fk_journal_entry_lines_journal_entry_id_journal_entries"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_journal_entry_lines")),
        sa.UniqueConstraint(
            "journal_entry_id",
            "line_number",
            name=op.f("uq_journal_entry_lines_journal_entry_id_line_number"),
        ),
    )


def downgrade() -> None:
    op.drop_table("journal_entry_lines")
    op.drop_index("ix_journal_entries_company_id_status_code", table_name="journal_entries")
    op.drop_index("ix_journal_entries_company_id_entry_date", table_name="journal_entries")
    op.drop_table("journal_entries")
    op.drop_table("fiscal_periods")
    op.drop_table("fiscal_years")
