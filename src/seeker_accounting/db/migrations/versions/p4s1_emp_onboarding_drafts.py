"""Phase 4.S1: Employee onboarding draft aggregate (Hire-to-Pay BP).

Adds the ``employee_onboarding_drafts`` table that backs the
:class:`EmployeeOnboardingService`. Drafts persist between sessions
so the user can leave and resume the hire BP. Once a draft completes,
its ``produced_employee_id`` points at the materialised employees row.

Migration is purely additive — no existing tables are altered.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "p4s1_emp_onboarding"
down_revision: Union[str, None] = "a14b00000007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "employee_onboarding_drafts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status_code", sa.String(length=40), nullable=False),
        sa.Column("current_step", sa.String(length=40), nullable=False),
        sa.Column(
            "payload_json",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "started_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "last_modified_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("abandoned_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("abandon_reason", sa.String(length=500), nullable=True),
        sa.Column(
            "produced_employee_id",
            sa.Integer(),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
    )
    op.create_index(
        "ix_employee_onboarding_drafts_company_id",
        "employee_onboarding_drafts",
        ["company_id"],
    )
    op.create_index(
        "ix_employee_onboarding_drafts_status",
        "employee_onboarding_drafts",
        ["status_code"],
    )
    op.create_index(
        "ix_employee_onboarding_drafts_employee_id",
        "employee_onboarding_drafts",
        ["produced_employee_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_employee_onboarding_drafts_employee_id",
        table_name="employee_onboarding_drafts",
    )
    op.drop_index(
        "ix_employee_onboarding_drafts_status",
        table_name="employee_onboarding_drafts",
    )
    op.drop_index(
        "ix_employee_onboarding_drafts_company_id",
        table_name="employee_onboarding_drafts",
    )
    op.drop_table("employee_onboarding_drafts")
