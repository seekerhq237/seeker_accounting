"""P7: Payroll Approvals & Segregation of Duties.

Adds the submitted_for_review workflow state columns to payroll_runs,
the sod_strict flag to company_payroll_settings, and the new
payroll_approver_configs routing table.

Revision ID: a14b00000013
Revises: a14b00000012
Create Date: 2026-05-10 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a14b00000013"
down_revision = "a14b00000012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── payroll_runs — approval workflow columns ───────────────────────────
    with op.batch_alter_table("payroll_runs") as batch:
        batch.add_column(
            sa.Column("submitted_at", sa.DateTime(), nullable=True)
        )
        batch.add_column(
            sa.Column(
                "submitted_by_user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="RESTRICT"),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column("sent_back_at", sa.DateTime(), nullable=True)
        )
        batch.add_column(
            sa.Column(
                "sent_back_by_user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="RESTRICT"),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column("sent_back_reason", sa.String(500), nullable=True)
        )
        batch.add_column(
            sa.Column(
                "approved_by_user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="RESTRICT"),
                nullable=True,
            )
        )

    # ── company_payroll_settings — SoD flag ────────────────────────────────
    with op.batch_alter_table("company_payroll_settings") as batch:
        batch.add_column(
            sa.Column(
                "sod_strict",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )

    # ── payroll_approver_configs — approval routing rules ──────────────────
    op.create_table(
        "payroll_approver_configs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "approver_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("min_run_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "ix_payroll_approver_configs_company",
        "payroll_approver_configs",
        ["company_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_payroll_approver_configs_company", table_name="payroll_approver_configs")
    op.drop_table("payroll_approver_configs")

    with op.batch_alter_table("company_payroll_settings") as batch:
        batch.drop_column("sod_strict")

    with op.batch_alter_table("payroll_runs") as batch:
        batch.drop_column("approved_by_user_id")
        batch.drop_column("sent_back_reason")
        batch.drop_column("sent_back_by_user_id")
        batch.drop_column("sent_back_at")
        batch.drop_column("submitted_by_user_id")
        batch.drop_column("submitted_at")
