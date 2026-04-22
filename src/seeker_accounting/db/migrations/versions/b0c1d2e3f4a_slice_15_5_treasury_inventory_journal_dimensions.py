"""slice_15_5_treasury_inventory_journal_dimensions

Revision ID: b0c1d2e3f4a
Revises: a9b0c1d2e3f4
Create Date: 2026-03-27

Slice 15.5 — Treasury, Inventory, and Journal Project Dimensions:
  - Extend treasury_transactions with contract_id and project_id
  - Extend treasury_transaction_lines with project dimension columns
  - Extend inventory_documents with contract_id and project_id
  - Extend inventory_document_lines with project dimension columns
  - Extend journal_entry_lines with project dimension columns
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b0c1d2e3f4a"
down_revision = "a9b0c1d2e3f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("treasury_transactions") as batch_op:
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

    with op.batch_alter_table("treasury_transaction_lines") as batch_op:
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
        batch_op.create_index("ix_treasury_transaction_lines_project_id", ["project_id"])
        batch_op.create_index("ix_treasury_transaction_lines_project_job_id", ["project_job_id"])

    with op.batch_alter_table("inventory_documents") as batch_op:
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

    with op.batch_alter_table("inventory_document_lines") as batch_op:
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
        batch_op.create_index("ix_inventory_document_lines_project_id", ["project_id"])
        batch_op.create_index("ix_inventory_document_lines_project_job_id", ["project_job_id"])

    with op.batch_alter_table("journal_entry_lines") as batch_op:
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
        batch_op.create_index("ix_journal_entry_lines_project_id", ["project_id"])
        batch_op.create_index("ix_journal_entry_lines_project_job_id", ["project_job_id"])
        batch_op.create_index("ix_journal_entry_lines_project_cost_code_id", ["project_cost_code_id"])


def downgrade() -> None:
    with op.batch_alter_table("journal_entry_lines") as batch_op:
        batch_op.drop_index("ix_journal_entry_lines_project_cost_code_id")
        batch_op.drop_index("ix_journal_entry_lines_project_job_id")
        batch_op.drop_index("ix_journal_entry_lines_project_id")
        batch_op.drop_column("project_cost_code_id")
        batch_op.drop_column("project_job_id")
        batch_op.drop_column("project_id")
        batch_op.drop_column("contract_id")

    with op.batch_alter_table("inventory_document_lines") as batch_op:
        batch_op.drop_index("ix_inventory_document_lines_project_job_id")
        batch_op.drop_index("ix_inventory_document_lines_project_id")
        batch_op.drop_column("project_cost_code_id")
        batch_op.drop_column("project_job_id")
        batch_op.drop_column("project_id")
        batch_op.drop_column("contract_id")

    with op.batch_alter_table("inventory_documents") as batch_op:
        batch_op.drop_column("project_id")
        batch_op.drop_column("contract_id")

    with op.batch_alter_table("treasury_transaction_lines") as batch_op:
        batch_op.drop_index("ix_treasury_transaction_lines_project_job_id")
        batch_op.drop_index("ix_treasury_transaction_lines_project_id")
        batch_op.drop_column("project_cost_code_id")
        batch_op.drop_column("project_job_id")
        batch_op.drop_column("project_id")
        batch_op.drop_column("contract_id")

    with op.batch_alter_table("treasury_transactions") as batch_op:
        batch_op.drop_column("project_id")
        batch_op.drop_column("contract_id")