"""P8/P9 payroll lifecycle and calculation transparency.

Adds run type/sequence support for off-cycle payroll, additive employee
corrections, persisted calculation traces, and company variance thresholds.

Revision ID: a14b00000016
Revises: a14b00000015
Create Date: 2026-05-15 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a14b00000016"
down_revision = "a14b00000015"
branch_labels = None
depends_on = None

_NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def upgrade() -> None:
    # payroll_runs: regular/off-cycle sequencing.
    with op.batch_alter_table(
        "payroll_runs", naming_convention=_NAMING_CONVENTION
    ) as batch:
        batch.add_column(
            sa.Column(
                "run_type_code",
                sa.String(length=20),
                nullable=False,
                server_default="regular",
            )
        )
        batch.add_column(
            sa.Column(
                "run_sequence",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )
        batch.add_column(
            sa.Column("off_cycle_reason_code", sa.String(length=40), nullable=True)
        )
        batch.add_column(sa.Column("off_cycle_employee_ids", sa.Text(), nullable=True))
        batch.add_column(sa.Column("source_run_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_payroll_runs_source_run_id_payroll_runs",
            "payroll_runs",
            ["source_run_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.drop_constraint(
            "uq_payroll_runs_company_id_period_year_period_month",
            type_="unique",
        )
        batch.create_unique_constraint(
            "uq_payroll_runs_company_id_period_year_period_month_run_type_code_run_sequence",
            [
                "company_id",
                "period_year",
                "period_month",
                "run_type_code",
                "run_sequence",
            ],
        )
    op.create_index(
        "ix_payroll_runs_company_period",
        "payroll_runs",
        ["company_id", "period_year", "period_month"],
    )

    # company_payroll_settings: variance thresholds.
    with op.batch_alter_table("company_payroll_settings") as batch:
        batch.add_column(
            sa.Column(
                "variance_threshold_percent",
                sa.Numeric(5, 2),
                nullable=False,
                server_default="10.00",
            )
        )
        batch.add_column(
            sa.Column("variance_per_component_thresholds", sa.Text(), nullable=True)
        )

    op.create_table(
        "employee_payroll_corrections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("component_id", sa.Integer(), nullable=False),
        sa.Column("period_year", sa.Integer(), nullable=False),
        sa.Column("period_month", sa.Integer(), nullable=False),
        sa.Column("correction_amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("reason_code", sa.String(length=40), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column(
            "status_code",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("source_run_id", sa.Integer(), nullable=True),
        sa.Column("applied_run_id", sa.Integer(), nullable=True),
        sa.Column("applied_run_employee_id", sa.Integer(), nullable=True),
        sa.Column("applied_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["component_id"], ["payroll_components.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["source_run_id"], ["payroll_runs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["applied_run_id"], ["payroll_runs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["applied_run_employee_id"],
            ["payroll_run_employees.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_employee_payroll_corrections_company_period",
        "employee_payroll_corrections",
        ["company_id", "period_year", "period_month"],
    )
    op.create_index(
        "ix_employee_payroll_corrections_employee",
        "employee_payroll_corrections",
        ["employee_id"],
    )
    op.create_index(
        "ix_employee_payroll_corrections_status",
        "employee_payroll_corrections",
        ["status_code"],
    )

    op.create_table(
        "payroll_calculation_traces",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("run_employee_id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("stage_code", sa.String(length=60), nullable=False),
        sa.Column("component_id", sa.Integer(), nullable=True),
        sa.Column("formula_code", sa.String(length=100), nullable=False),
        sa.Column("input_json", sa.Text(), nullable=True),
        sa.Column("output_json", sa.Text(), nullable=True),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], ["payroll_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["run_employee_id"], ["payroll_run_employees.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["component_id"], ["payroll_components.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_payroll_calculation_traces_run",
        "payroll_calculation_traces",
        ["run_id"],
    )
    op.create_index(
        "ix_payroll_calculation_traces_run_employee",
        "payroll_calculation_traces",
        ["run_employee_id"],
    )
    op.create_index(
        "ix_payroll_calculation_traces_employee",
        "payroll_calculation_traces",
        ["employee_id"],
    )
    op.create_index(
        "ix_payroll_calculation_traces_component",
        "payroll_calculation_traces",
        ["component_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_payroll_calculation_traces_component",
        table_name="payroll_calculation_traces",
    )
    op.drop_index(
        "ix_payroll_calculation_traces_employee",
        table_name="payroll_calculation_traces",
    )
    op.drop_index(
        "ix_payroll_calculation_traces_run_employee",
        table_name="payroll_calculation_traces",
    )
    op.drop_index(
        "ix_payroll_calculation_traces_run",
        table_name="payroll_calculation_traces",
    )
    op.drop_table("payroll_calculation_traces")

    op.drop_index(
        "ix_employee_payroll_corrections_status",
        table_name="employee_payroll_corrections",
    )
    op.drop_index(
        "ix_employee_payroll_corrections_employee",
        table_name="employee_payroll_corrections",
    )
    op.drop_index(
        "ix_employee_payroll_corrections_company_period",
        table_name="employee_payroll_corrections",
    )
    op.drop_table("employee_payroll_corrections")

    with op.batch_alter_table("company_payroll_settings") as batch:
        batch.drop_column("variance_per_component_thresholds")
        batch.drop_column("variance_threshold_percent")

    op.drop_index("ix_payroll_runs_company_period", table_name="payroll_runs")
    with op.batch_alter_table(
        "payroll_runs", naming_convention=_NAMING_CONVENTION
    ) as batch:
        batch.drop_constraint(
            "uq_payroll_runs_company_id_period_year_period_month_run_type_code_run_sequence",
            type_="unique",
        )
        batch.create_unique_constraint(
            "uq_payroll_runs_company_id_period_year_period_month",
            ["company_id", "period_year", "period_month"],
        )
        batch.drop_constraint("fk_payroll_runs_source_run_id_payroll_runs", type_="foreignkey")
        batch.drop_column("source_run_id")
        batch.drop_column("off_cycle_employee_ids")
        batch.drop_column("off_cycle_reason_code")
        batch.drop_column("run_sequence")
        batch.drop_column("run_type_code")