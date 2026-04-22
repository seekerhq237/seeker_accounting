"""Slice 14.1: Project-control setup foundation

Revision ID: 07c5651fc193
Revises: f6a7b8c9d0e1
Create Date: 2026-03-27 01:55:56.753005
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision = '07c5651fc193'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── company_project_preferences ───────────────────────────────────────────
    op.create_table(
        "company_project_preferences",
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column(
            "allow_projects_without_contract",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("default_budget_control_mode_code", sa.String(20), nullable=False),
        sa.Column("default_commitment_control_mode_code", sa.String(20), nullable=False),
        sa.Column("budget_warning_percent_threshold", sa.Numeric(5, 2), nullable=True),
        sa.Column(
            "require_job_on_cost_posting",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "require_cost_code_on_cost_posting",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("company_id"),
    )


def downgrade() -> None:
    op.drop_table("company_project_preferences")
