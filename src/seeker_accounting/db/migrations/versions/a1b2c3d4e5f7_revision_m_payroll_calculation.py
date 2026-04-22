"""Revision M: Payroll Calculation Engine.

Creates 7 new tables for the Slice 13B payroll calculation engine:
    employee_compensation_profiles   — base salary and contract parameters per employee
    employee_component_assignments   — recurring component assignments per employee
    payroll_input_batches            — batches of approved variable payroll inputs
    payroll_input_lines              — individual variable input entries per batch
    payroll_runs                     — payroll run headers per company/period
    payroll_run_employees            — per-employee summary rows for a run (6 bases)
    payroll_run_lines                — individual component result lines per employee per run

All tables are additive. No existing tables are modified.
GL posting is out of scope for this slice.

Revision ID: a1b2c3d4e5f7
Revises: c769a70b05ed
Create Date: 2026-03-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f7"
down_revision = "c769a70b05ed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── employee_compensation_profiles ────────────────────────────────────────
    op.create_table(
        "employee_compensation_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("profile_name", sa.String(length=100), nullable=False),
        sa.Column("basic_salary", sa.Numeric(18, 4), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["currency_code"], ["currencies.code"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "employee_id", "effective_from"),
    )
    op.create_index("ix_emp_comp_profiles_company_id", "employee_compensation_profiles", ["company_id"])
    op.create_index("ix_emp_comp_profiles_employee_id", "employee_compensation_profiles", ["employee_id"])

    # ── employee_component_assignments ────────────────────────────────────────
    op.create_table(
        "employee_component_assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("component_id", sa.Integer(), nullable=False),
        sa.Column("override_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("override_rate", sa.Numeric(12, 6), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["component_id"], ["payroll_components.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "employee_id", "component_id", "effective_from"),
    )
    op.create_index("ix_emp_comp_assignments_company_id", "employee_component_assignments", ["company_id"])
    op.create_index("ix_emp_comp_assignments_employee_id", "employee_component_assignments", ["employee_id"])

    # ── payroll_input_batches ──────────────────────────────────────────────────
    op.create_table(
        "payroll_input_batches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("batch_reference", sa.String(length=30), nullable=False),
        sa.Column("period_year", sa.Integer(), nullable=False),
        sa.Column("period_month", sa.Integer(), nullable=False),
        sa.Column("status_code", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("description", sa.String(length=200), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "batch_reference"),
    )
    op.create_index("ix_payroll_input_batches_company_id", "payroll_input_batches", ["company_id"])
    op.create_index("ix_payroll_input_batches_period", "payroll_input_batches", ["company_id", "period_year", "period_month"])

    # ── payroll_input_lines ────────────────────────────────────────────────────
    op.create_table(
        "payroll_input_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("component_id", sa.Integer(), nullable=False),
        sa.Column("input_amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("input_quantity", sa.Numeric(12, 4), nullable=True),
        sa.Column("notes", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["batch_id"], ["payroll_input_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["component_id"], ["payroll_components.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payroll_input_lines_batch_id", "payroll_input_lines", ["batch_id"])
    op.create_index("ix_payroll_input_lines_employee_id", "payroll_input_lines", ["employee_id"])

    # ── payroll_runs ───────────────────────────────────────────────────────────
    op.create_table(
        "payroll_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("run_reference", sa.String(length=30), nullable=False),
        sa.Column("run_label", sa.String(length=100), nullable=False),
        sa.Column("period_year", sa.Integer(), nullable=False),
        sa.Column("period_month", sa.Integer(), nullable=False),
        sa.Column("status_code", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("run_date", sa.Date(), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("calculated_at", sa.DateTime(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["currency_code"], ["currencies.code"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "run_reference"),
        sa.UniqueConstraint("company_id", "period_year", "period_month"),
    )
    op.create_index("ix_payroll_runs_company_id", "payroll_runs", ["company_id"])

    # ── payroll_run_employees ──────────────────────────────────────────────────
    op.create_table(
        "payroll_run_employees",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("gross_earnings", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("taxable_salary_base", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("tdl_base", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("cnps_contributory_base", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("employer_cost_base", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("net_payable", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("total_earnings", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("total_employee_deductions", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("total_employer_contributions", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("total_taxes", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("status_code", sa.String(length=20), nullable=False, server_default="included"),
        sa.Column("calculation_notes", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], ["payroll_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "run_id", "employee_id"),
    )
    op.create_index("ix_payroll_run_employees_run_id", "payroll_run_employees", ["run_id"])
    op.create_index("ix_payroll_run_employees_employee_id", "payroll_run_employees", ["employee_id"])

    # ── payroll_run_lines ──────────────────────────────────────────────────────
    op.create_table(
        "payroll_run_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("run_employee_id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("component_id", sa.Integer(), nullable=False),
        sa.Column("component_type_code", sa.String(length=30), nullable=False),
        sa.Column("calculation_basis", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("rate_applied", sa.Numeric(12, 6), nullable=True),
        sa.Column("component_amount", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], ["payroll_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_employee_id"], ["payroll_run_employees.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["component_id"], ["payroll_components.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payroll_run_lines_run_id", "payroll_run_lines", ["run_id"])
    op.create_index("ix_payroll_run_lines_run_employee_id", "payroll_run_lines", ["run_employee_id"])
    op.create_index("ix_payroll_run_lines_employee_id", "payroll_run_lines", ["employee_id"])


def downgrade() -> None:
    op.drop_table("payroll_run_lines")
    op.drop_table("payroll_run_employees")
    op.drop_table("payroll_runs")
    op.drop_table("payroll_input_lines")
    op.drop_table("payroll_input_batches")
    op.drop_table("employee_component_assignments")
    op.drop_table("employee_compensation_profiles")
