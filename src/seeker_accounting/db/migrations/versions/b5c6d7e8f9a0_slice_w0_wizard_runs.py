"""Slice W0: wizard framework — wizard_runs table.

Adds the ``wizard_runs`` table that powers resumable wizards (Company Setup,
Month-End Close, Payroll Run, etc.). See ``docs/Wizards.md``.

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-04-28 10:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b5c6d7e8f9a0"
down_revision: Union[str, None] = "a4b5c6d7e8f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "wizard_runs",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("wizard_code", sa.String(length=60), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=True),
        sa.Column("initiated_by_user_id", sa.Integer(), nullable=False),
        sa.Column("current_step_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_step_key", sa.String(length=60), nullable=True),
        sa.Column("status_code", sa.String(length=20), nullable=False),
        sa.Column("state_payload", sa.Text(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], ondelete="SET NULL",
            name="fk_wizard_runs_company_id_companies",
        ),
        sa.ForeignKeyConstraint(
            ["initiated_by_user_id"], ["users.id"], ondelete="RESTRICT",
            name="fk_wizard_runs_initiated_by_user_id_users",
        ),
    )
    op.create_index(
        "ix_wizard_runs_company_id",
        "wizard_runs",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        "ix_wizard_runs_user_status",
        "wizard_runs",
        ["initiated_by_user_id", "status_code"],
        unique=False,
    )
    op.create_index(
        "ix_wizard_runs_wizard_code",
        "wizard_runs",
        ["wizard_code"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_wizard_runs_wizard_code", table_name="wizard_runs")
    op.drop_index("ix_wizard_runs_user_status", table_name="wizard_runs")
    op.drop_index("ix_wizard_runs_company_id", table_name="wizard_runs")
    op.drop_table("wizard_runs")
