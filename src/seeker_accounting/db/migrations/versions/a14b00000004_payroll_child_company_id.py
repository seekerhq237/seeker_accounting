"""Add company_id scoping to payroll child tables.

Revision ID: a14b00000004
Revises: a14b00000003
Create Date: 2026-04-29

Audit finding (Schema scoping): two payroll child tables relied solely on
parent FK CASCADE for company isolation:

    - ``payroll_run_employee_project_allocations``
    - ``payroll_remittance_lines``

While the parent rows are company-scoped, the children themselves carried
no ``company_id`` column. This migration:

1. Adds a ``company_id`` column to each table (nullable initially so the
   backfill can succeed against existing data).
2. Backfills ``company_id`` from the parent row's company:
     - allocations  ← payroll_run_employees.company_id
     - remittance lines ← payroll_remittance_batches.company_id
3. Makes the column NOT NULL and adds defensive composite indexes.

Downgrade simply drops the indexes and the columns.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# Alembic identifiers
revision = "a14b00000004"
down_revision = "a14b00000003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # ── payroll_run_employee_project_allocations ──────────────────────────────
    with op.batch_alter_table("payroll_run_employee_project_allocations") as batch:
        batch.add_column(
            sa.Column(
                "company_id",
                sa.Integer(),
                sa.ForeignKey("companies.id", ondelete="RESTRICT"),
                nullable=True,
            )
        )

    bind.execute(
        sa.text(
            """
            UPDATE payroll_run_employee_project_allocations
            SET company_id = (
                SELECT pre.company_id
                FROM payroll_run_employees pre
                WHERE pre.id = payroll_run_employee_project_allocations.payroll_run_employee_id
            )
            WHERE company_id IS NULL
            """
        )
    )

    with op.batch_alter_table("payroll_run_employee_project_allocations") as batch:
        batch.alter_column("company_id", existing_type=sa.Integer(), nullable=False)
        batch.create_index(
            "ix_payroll_run_employee_project_allocations_company_project",
            ["company_id", "project_id"],
        )

    # ── payroll_remittance_lines ──────────────────────────────────────────────
    with op.batch_alter_table("payroll_remittance_lines") as batch:
        batch.add_column(
            sa.Column(
                "company_id",
                sa.Integer(),
                sa.ForeignKey("companies.id", ondelete="RESTRICT"),
                nullable=True,
            )
        )

    bind.execute(
        sa.text(
            """
            UPDATE payroll_remittance_lines
            SET company_id = (
                SELECT b.company_id
                FROM payroll_remittance_batches b
                WHERE b.id = payroll_remittance_lines.payroll_remittance_batch_id
            )
            WHERE company_id IS NULL
            """
        )
    )

    with op.batch_alter_table("payroll_remittance_lines") as batch:
        batch.alter_column("company_id", existing_type=sa.Integer(), nullable=False)
        batch.create_index(
            "ix_payroll_remittance_lines_company_status",
            ["company_id", "status_code"],
        )


def downgrade() -> None:
    with op.batch_alter_table("payroll_remittance_lines") as batch:
        batch.drop_index("ix_payroll_remittance_lines_company_status")
        batch.drop_column("company_id")

    with op.batch_alter_table("payroll_run_employee_project_allocations") as batch:
        batch.drop_index("ix_payroll_run_employee_project_allocations_company_project")
        batch.drop_column("company_id")
