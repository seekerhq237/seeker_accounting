"""slice_15_4_sales_purchase_project_dimensions

Revision ID: a9b0c1d2e3f4
Revises: f8a9b0c1d2e3
Create Date: 2026-03-27

Slice 15.4 — Sales and Purchase Project Dimensions:
  - Extend sales_invoices with contract_id and project_id
  - Extend sales_invoice_lines with project dimension columns
  - Extend purchase_bills with contract_id and project_id
  - Extend purchase_bill_lines with project dimension columns
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a9b0c1d2e3f4"
down_revision = "f8a9b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("sales_invoices") as batch_op:
        batch_op.add_column(
            sa.Column(
                "contract_id",
                sa.Integer(),
                sa.ForeignKey("contracts.id", ondelete="RESTRICT"),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "project_id",
                sa.Integer(),
                sa.ForeignKey("projects.id", ondelete="RESTRICT"),
                nullable=True,
            )
        )

    with op.batch_alter_table("sales_invoice_lines") as batch_op:
        batch_op.add_column(
            sa.Column(
                "contract_id",
                sa.Integer(),
                sa.ForeignKey("contracts.id", ondelete="RESTRICT"),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "project_id",
                sa.Integer(),
                sa.ForeignKey("projects.id", ondelete="RESTRICT"),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "project_job_id",
                sa.Integer(),
                sa.ForeignKey("project_jobs.id", ondelete="RESTRICT"),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "project_cost_code_id",
                sa.Integer(),
                sa.ForeignKey("project_cost_codes.id", ondelete="RESTRICT"),
                nullable=True,
            )
        )
        batch_op.create_index("ix_sales_invoice_lines_project_id", ["project_id"])
        batch_op.create_index("ix_sales_invoice_lines_project_job_id", ["project_job_id"])

    with op.batch_alter_table("purchase_bills") as batch_op:
        batch_op.add_column(
            sa.Column(
                "contract_id",
                sa.Integer(),
                sa.ForeignKey("contracts.id", ondelete="RESTRICT"),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "project_id",
                sa.Integer(),
                sa.ForeignKey("projects.id", ondelete="RESTRICT"),
                nullable=True,
            )
        )

    with op.batch_alter_table("purchase_bill_lines") as batch_op:
        batch_op.add_column(
            sa.Column(
                "contract_id",
                sa.Integer(),
                sa.ForeignKey("contracts.id", ondelete="RESTRICT"),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "project_id",
                sa.Integer(),
                sa.ForeignKey("projects.id", ondelete="RESTRICT"),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "project_job_id",
                sa.Integer(),
                sa.ForeignKey("project_jobs.id", ondelete="RESTRICT"),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "project_cost_code_id",
                sa.Integer(),
                sa.ForeignKey("project_cost_codes.id", ondelete="RESTRICT"),
                nullable=True,
            )
        )
        batch_op.create_index("ix_purchase_bill_lines_project_id", ["project_id"])
        batch_op.create_index("ix_purchase_bill_lines_project_job_id", ["project_job_id"])


def downgrade() -> None:
    with op.batch_alter_table("purchase_bill_lines") as batch_op:
        batch_op.drop_index("ix_purchase_bill_lines_project_job_id")
        batch_op.drop_index("ix_purchase_bill_lines_project_id")
        batch_op.drop_column("project_cost_code_id")
        batch_op.drop_column("project_job_id")
        batch_op.drop_column("project_id")
        batch_op.drop_column("contract_id")

    with op.batch_alter_table("purchase_bills") as batch_op:
        batch_op.drop_column("project_id")
        batch_op.drop_column("contract_id")

    with op.batch_alter_table("sales_invoice_lines") as batch_op:
        batch_op.drop_index("ix_sales_invoice_lines_project_job_id")
        batch_op.drop_index("ix_sales_invoice_lines_project_id")
        batch_op.drop_column("project_cost_code_id")
        batch_op.drop_column("project_job_id")
        batch_op.drop_column("project_id")
        batch_op.drop_column("contract_id")

    with op.batch_alter_table("sales_invoices") as batch_op:
        batch_op.drop_column("project_id")
        batch_op.drop_column("contract_id")
