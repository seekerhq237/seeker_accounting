"""Revision L: Payroll Foundation.

Creates the 7 base tables for the payroll module:
    company_payroll_settings  — one-to-one company payroll config anchor
    departments               — company-scoped org departments
    positions                 — company-scoped org positions
    employees                 — employee master records
    payroll_components        — configurable earning/deduction/contribution definitions
    payroll_rule_sets         — effective-dated rule set headers (PIT, CNPS, etc.)
    payroll_rule_brackets     — bracket/band lines within a rule set

All tables are additive. No existing tables are modified.
No statutory seed data is inserted — that belongs to a controlled seed workflow.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-03-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── company_payroll_settings ──────────────────────────────────────────────
    op.create_table(
        "company_payroll_settings",
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("statutory_pack_version_code", sa.String(50), nullable=True),
        sa.Column("cnps_regime_code", sa.String(30), nullable=True),
        sa.Column("accident_risk_class_code", sa.String(30), nullable=True),
        sa.Column("default_pay_frequency_code", sa.String(20), nullable=False),
        sa.Column("default_payroll_currency_code", sa.String(3), nullable=False),
        sa.Column("overtime_policy_mode_code", sa.String(30), nullable=True),
        sa.Column("benefit_in_kind_policy_mode_code", sa.String(30), nullable=True),
        sa.Column("payroll_number_prefix", sa.String(20), nullable=True),
        sa.Column("payroll_number_padding_width", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["default_payroll_currency_code"], ["currencies.code"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("company_id"),
    )

    # ── departments ───────────────────────────────────────────────────────────
    op.create_table(
        "departments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "code"),
    )
    op.create_index("ix_departments_company_id", "departments", ["company_id"])

    # ── positions ─────────────────────────────────────────────────────────────
    op.create_table(
        "positions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "code"),
    )
    op.create_index("ix_positions_company_id", "positions", ["company_id"])

    # ── employees ─────────────────────────────────────────────────────────────
    op.create_table(
        "employees",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("employee_number", sa.String(30), nullable=False),
        sa.Column("display_name", sa.String(150), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("department_id", sa.Integer(), nullable=True),
        sa.Column("position_id", sa.Integer(), nullable=True),
        sa.Column("hire_date", sa.Date(), nullable=False),
        sa.Column("termination_date", sa.Date(), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("tax_identifier", sa.String(100), nullable=True),
        sa.Column("base_currency_code", sa.String(3), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["position_id"], ["positions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["base_currency_code"], ["currencies.code"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "employee_number"),
    )
    op.create_index("ix_employees_company_id", "employees", ["company_id"])
    op.create_index("ix_employees_department_id", "employees", ["department_id"])
    op.create_index("ix_employees_position_id", "employees", ["position_id"])

    # ── payroll_components ────────────────────────────────────────────────────
    op.create_table(
        "payroll_components",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("component_code", sa.String(30), nullable=False),
        sa.Column("component_name", sa.String(100), nullable=False),
        sa.Column("component_type_code", sa.String(30), nullable=False),
        sa.Column("calculation_method_code", sa.String(30), nullable=False),
        sa.Column(
            "is_taxable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "is_pensionable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("expense_account_id", sa.Integer(), nullable=True),
        sa.Column("liability_account_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["expense_account_id"], ["accounts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["liability_account_id"], ["accounts.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "component_code"),
    )
    op.create_index(
        "ix_payroll_components_company_id", "payroll_components", ["company_id"]
    )

    # ── payroll_rule_sets ─────────────────────────────────────────────────────
    op.create_table(
        "payroll_rule_sets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("rule_code", sa.String(30), nullable=False),
        sa.Column("rule_name", sa.String(100), nullable=False),
        sa.Column("rule_type_code", sa.String(30), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("calculation_basis_code", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "rule_code", "effective_from"),
    )
    op.create_index(
        "ix_payroll_rule_sets_company_id", "payroll_rule_sets", ["company_id"]
    )
    op.create_index(
        "ix_payroll_rule_sets_rule_code",
        "payroll_rule_sets",
        ["company_id", "rule_code"],
    )

    # ── payroll_rule_brackets ─────────────────────────────────────────────────
    op.create_table(
        "payroll_rule_brackets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("payroll_rule_set_id", sa.Integer(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("lower_bound_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("upper_bound_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("rate_percent", sa.Numeric(8, 4), nullable=True),
        sa.Column("fixed_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("deduction_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("cap_amount", sa.Numeric(18, 4), nullable=True),
        sa.ForeignKeyConstraint(
            ["payroll_rule_set_id"], ["payroll_rule_sets.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payroll_rule_set_id", "line_number"),
    )
    op.create_index(
        "ix_payroll_rule_brackets_rule_set_id",
        "payroll_rule_brackets",
        ["payroll_rule_set_id"],
    )


def downgrade() -> None:
    op.drop_table("payroll_rule_brackets")
    op.drop_table("payroll_rule_sets")
    op.drop_table("payroll_components")
    op.drop_table("employees")
    op.drop_table("positions")
    op.drop_table("departments")
    op.drop_table("company_payroll_settings")
