"""add project_budget_versions and project_budget_lines tables (Slice 15.1)

Revision ID: c5e6f7a8b9d0
Revises: b4d5e6f7a8c9
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c5e6f7a8b9d0"
down_revision: Union[str, None] = "b4d5e6f7a8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_budget_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("version_name", sa.String(255), nullable=False),
        sa.Column("version_type_code", sa.String(20), nullable=False),
        sa.Column("status_code", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("base_version_id", sa.Integer(), nullable=True),
        sa.Column("budget_date", sa.Date(), nullable=False),
        sa.Column("revision_reason", sa.Text(), nullable=True),
        sa.Column("total_budget_amount", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("approved_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_pbv_company"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_pbv_project"),
        sa.ForeignKeyConstraint(
            ["base_version_id"], ["project_budget_versions.id"], name="fk_pbv_base_version"
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"], ["users.id"], name="fk_pbv_approved_by_user"
        ),
        sa.UniqueConstraint(
            "project_id", "version_number", name="uq_project_budget_versions_project_version"
        ),
    )
    op.create_index("ix_project_budget_versions_company_id", "project_budget_versions", ["company_id"])
    op.create_index("ix_project_budget_versions_project_id", "project_budget_versions", ["project_id"])

    op.create_table(
        "project_budget_lines",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_budget_version_id", sa.Integer(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("project_job_id", sa.Integer(), nullable=True),
        sa.Column("project_cost_code_id", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("quantity", sa.Numeric(15, 4), nullable=True),
        sa.Column("unit_rate", sa.Numeric(15, 4), nullable=True),
        sa.Column("line_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["project_budget_version_id"], ["project_budget_versions.id"],
            name="fk_pbl_version",
        ),
        sa.ForeignKeyConstraint(
            ["project_job_id"], ["project_jobs.id"], name="fk_pbl_job"
        ),
        sa.ForeignKeyConstraint(
            ["project_cost_code_id"], ["project_cost_codes.id"], name="fk_pbl_cost_code"
        ),
        sa.UniqueConstraint(
            "project_budget_version_id", "line_number",
            name="uq_project_budget_lines_version_line",
        ),
    )
    op.create_index(
        "ix_project_budget_lines_version_id",
        "project_budget_lines",
        ["project_budget_version_id"],
    )


def downgrade() -> None:
    op.drop_table("project_budget_lines")
    op.drop_table("project_budget_versions")
