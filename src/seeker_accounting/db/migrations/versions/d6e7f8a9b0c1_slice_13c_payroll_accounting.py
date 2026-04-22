"""slice_13c_payroll_accounting

Revision ID: d6e7f8a9b0c1
Revises: c5e6f7a8b9d0
Create Date: 2026-03-27

Slice 13C — Payroll Accounting:
  - Extend payroll_runs: posted_at, posted_by_user_id, posted_journal_entry_id
  - Extend payroll_run_employees: payment_status_code, payment_date
  - Create payroll_payment_records
  - Create payroll_remittance_batches
  - Create payroll_remittance_lines
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d6e7f8a9b0c1"
down_revision = "c5e6f7a8b9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Extend payroll_runs ────────────────────────────────────────────────────
    with op.batch_alter_table("payroll_runs") as batch_op:
        batch_op.add_column(
            sa.Column("posted_at", sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "posted_by_user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="RESTRICT"),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "posted_journal_entry_id",
                sa.Integer(),
                sa.ForeignKey("journal_entries.id", ondelete="RESTRICT"),
                nullable=True,
            )
        )

    # ── Extend payroll_run_employees ───────────────────────────────────────────
    with op.batch_alter_table("payroll_run_employees") as batch_op:
        batch_op.add_column(
            sa.Column(
                "payment_status_code",
                sa.String(20),
                nullable=False,
                server_default="unpaid",
            )
        )
        batch_op.add_column(
            sa.Column("payment_date", sa.Date(), nullable=True)
        )

    # ── payroll_payment_records ────────────────────────────────────────────────
    op.create_table(
        "payroll_payment_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "run_employee_id",
            sa.Integer(),
            sa.ForeignKey("payroll_run_employees.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("amount_paid", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("payment_method_code", sa.String(30), nullable=True),
        sa.Column("payment_reference", sa.String(120), nullable=True),
        sa.Column(
            "treasury_transaction_id",
            sa.Integer(),
            sa.ForeignKey("treasury_transactions.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "updated_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_payroll_payment_records_run_employee",
        "payroll_payment_records",
        ["run_employee_id"],
    )
    op.create_index(
        "ix_payroll_payment_records_company_date",
        "payroll_payment_records",
        ["company_id", "payment_date"],
    )

    # ── payroll_remittance_batches ─────────────────────────────────────────────
    op.create_table(
        "payroll_remittance_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("batch_number", sa.String(30), nullable=False),
        sa.Column(
            "payroll_run_id",
            sa.Integer(),
            sa.ForeignKey("payroll_runs.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("period_start_date", sa.Date(), nullable=False),
        sa.Column("period_end_date", sa.Date(), nullable=False),
        sa.Column("remittance_authority_code", sa.String(30), nullable=False),
        sa.Column("remittance_date", sa.Date(), nullable=True),
        sa.Column("amount_due", sa.Numeric(precision=18, scale=4), nullable=False, server_default="0"),
        sa.Column("amount_paid", sa.Numeric(precision=18, scale=4), nullable=False, server_default="0"),
        sa.Column("status_code", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("reference", sa.String(120), nullable=True),
        sa.Column(
            "treasury_transaction_id",
            sa.Integer(),
            sa.ForeignKey("treasury_transactions.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "updated_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "batch_number", name="uq_payroll_remittance_batch_number"),
    )
    op.create_index(
        "ix_payroll_remittance_batches_company",
        "payroll_remittance_batches",
        ["company_id"],
    )
    op.create_index(
        "ix_payroll_remittance_batches_run",
        "payroll_remittance_batches",
        ["payroll_run_id"],
    )

    # ── payroll_remittance_lines ───────────────────────────────────────────────
    op.create_table(
        "payroll_remittance_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "payroll_remittance_batch_id",
            sa.Integer(),
            sa.ForeignKey("payroll_remittance_batches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column(
            "payroll_component_id",
            sa.Integer(),
            sa.ForeignKey("payroll_components.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "liability_account_id",
            sa.Integer(),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("amount_due", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("amount_paid", sa.Numeric(precision=18, scale=4), nullable=False, server_default="0"),
        sa.Column("status_code", sa.String(20), nullable=False, server_default="open"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "payroll_remittance_batch_id", "line_number",
            name="uq_payroll_remittance_line_number",
        ),
    )
    op.create_index(
        "ix_payroll_remittance_lines_batch",
        "payroll_remittance_lines",
        ["payroll_remittance_batch_id"],
    )


def downgrade() -> None:
    op.drop_table("payroll_remittance_lines")
    op.drop_table("payroll_remittance_batches")
    op.drop_table("payroll_payment_records")

    with op.batch_alter_table("payroll_run_employees") as batch_op:
        batch_op.drop_column("payment_date")
        batch_op.drop_column("payment_status_code")

    with op.batch_alter_table("payroll_runs") as batch_op:
        batch_op.drop_column("posted_journal_entry_id")
        batch_op.drop_column("posted_by_user_id")
        batch_op.drop_column("posted_at")
