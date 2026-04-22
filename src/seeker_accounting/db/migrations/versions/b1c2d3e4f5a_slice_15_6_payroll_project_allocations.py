"""slice_15_6_payroll_project_allocations

Revision ID: b1c2d3e4f5a
Revises: b0c1d2e3f4a
Create Date: 2026-03-27

Slice 15.6 — Payroll Project Allocation Bridge:
  - Add payroll_run_employee_project_allocations
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b1c2d3e4f5a"
down_revision = "b0c1d2e3f4a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payroll_run_employee_project_allocations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("payroll_run_employee_id", sa.Integer(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("contract_id", sa.Integer(), nullable=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("project_job_id", sa.Integer(), nullable=True),
        sa.Column("project_cost_code_id", sa.Integer(), nullable=True),
        sa.Column("allocation_basis_code", sa.String(length=20), nullable=False),
        sa.Column("allocation_quantity", sa.Numeric(18, 4), nullable=True),
        sa.Column("allocation_percent", sa.Numeric(9, 4), nullable=True),
        sa.Column("allocated_cost_amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["contract_id"],
            ["contracts.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["payroll_run_employee_id"],
            ["payroll_run_employees.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_cost_code_id"],
            ["project_cost_codes.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_job_id"],
            ["project_jobs.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payroll_run_employee_id", "line_number"),
    )
    op.create_index(
        "ix_payroll_run_employee_project_allocations_run_employee_id",
        "payroll_run_employee_project_allocations",
        ["payroll_run_employee_id"],
    )
    op.create_index(
        "ix_payroll_run_employee_project_allocations_project_job",
        "payroll_run_employee_project_allocations",
        ["project_id", "project_job_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_payroll_run_employee_project_allocations_project_job",
        table_name="payroll_run_employee_project_allocations",
    )
    op.drop_index(
        "ix_payroll_run_employee_project_allocations_run_employee_id",
        table_name="payroll_run_employee_project_allocations",
    )
    op.drop_table("payroll_run_employee_project_allocations")
