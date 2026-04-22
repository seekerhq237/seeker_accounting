"""add project_jobs and project_cost_codes tables (Slice 14.4)

Revision ID: b4d5e6f7a8c9
Revises: 8f3a2c9d1e47
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b4d5e6f7a8c9"
down_revision: Union[str, None] = "8f3a2c9d1e47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("job_code", sa.String(40), nullable=False),
        sa.Column("job_name", sa.String(255), nullable=False),
        sa.Column("parent_job_id", sa.Integer(), sa.ForeignKey("project_jobs.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("sequence_number", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status_code", sa.String(20), nullable=False, server_default="active"),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("planned_end_date", sa.Date(), nullable=True),
        sa.Column("actual_end_date", sa.Date(), nullable=True),
        sa.Column("allow_direct_cost_posting", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("project_id", "job_code"),
    )
    op.create_index("ix_project_jobs_project_id", "project_jobs", ["project_id"])
    op.create_index("ix_project_jobs_parent_job_id", "project_jobs", ["parent_job_id"])
    op.create_index("ix_project_jobs_company_id", "project_jobs", ["company_id"])

    op.create_table(
        "project_cost_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("cost_code_type_code", sa.String(30), nullable=False),
        sa.Column("default_account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "code"),
    )
    op.create_index("ix_project_cost_codes_company_id", "project_cost_codes", ["company_id"])


def downgrade() -> None:
    op.drop_index("ix_project_cost_codes_company_id", table_name="project_cost_codes")
    op.drop_table("project_cost_codes")

    op.drop_index("ix_project_jobs_company_id", table_name="project_jobs")
    op.drop_index("ix_project_jobs_parent_job_id", table_name="project_jobs")
    op.drop_index("ix_project_jobs_project_id", table_name="project_jobs")
    op.drop_table("project_jobs")
