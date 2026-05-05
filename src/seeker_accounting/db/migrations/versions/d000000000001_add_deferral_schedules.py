"""Add deferral_schedules and deferral_schedule_lines tables.

Revision ID: d000000000001
Revises: a14b00000023
Create Date: 2026-05-05

Adds two tables for the accounting deferrals module:
  - deferral_schedules        — master record per prepaid/unearned item
  - deferral_schedule_lines   — one recognition instalment per period
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d000000000001"
down_revision = "a14b00000023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deferral_schedules",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("deferral_type", sa.String(10), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("reference_text", sa.String(120), nullable=True),
        sa.Column(
            "recognition_account_id",
            sa.Integer(),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "holding_account_id",
            sa.Integer(),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("total_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("period_count", sa.Integer(), nullable=False),
        sa.Column("status_code", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("source_document_type", sa.String(50), nullable=True),
        sa.Column("source_document_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("total_amount > 0", name="ck_deferral_schedules_total_positive"),
        sa.CheckConstraint("period_count > 0", name="ck_deferral_schedules_period_count_positive"),
    )
    op.create_index(
        "ix_deferral_schedules_company_id",
        "deferral_schedules",
        ["company_id"],
    )
    op.create_index(
        "ix_deferral_schedules_company_id_status",
        "deferral_schedules",
        ["company_id", "status_code"],
    )

    op.create_table(
        "deferral_schedule_lines",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "deferral_schedule_id",
            sa.Integer(),
            sa.ForeignKey("deferral_schedules.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("recognition_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("status_code", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column(
            "journal_entry_id",
            sa.Integer(),
            sa.ForeignKey("journal_entries.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("amount >= 0", name="ck_deferral_line_amount_non_negative"),
        sa.UniqueConstraint(
            "deferral_schedule_id", "line_number", name="uq_deferral_line_number"
        ),
    )
    op.create_index(
        "ix_deferral_schedule_lines_schedule_id",
        "deferral_schedule_lines",
        ["deferral_schedule_id"],
    )
    op.create_index(
        "ix_deferral_schedule_lines_status",
        "deferral_schedule_lines",
        ["deferral_schedule_id", "status_code"],
    )


def downgrade() -> None:
    op.drop_index("ix_deferral_schedule_lines_status", "deferral_schedule_lines")
    op.drop_index("ix_deferral_schedule_lines_schedule_id", "deferral_schedule_lines")
    op.drop_table("deferral_schedule_lines")

    op.drop_index("ix_deferral_schedules_company_id_status", "deferral_schedules")
    op.drop_index("ix_deferral_schedules_company_id", "deferral_schedules")
    op.drop_table("deferral_schedules")
