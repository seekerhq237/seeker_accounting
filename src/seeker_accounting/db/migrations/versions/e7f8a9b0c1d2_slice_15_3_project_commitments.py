"""slice_15_3_project_commitments

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-04-15

Slice 15.3 — Project Commitments:
  - Create project_commitments
  - Create project_commitment_lines
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e7f8a9b0c1d2"
down_revision = "d6e7f8a9b0c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── project_commitments ────────────────────────────────────────────────────
    op.create_table(
        "project_commitments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("commitment_number", sa.String(40), nullable=False),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "supplier_id",
            sa.Integer(),
            sa.ForeignKey("suppliers.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("commitment_type_code", sa.String(30), nullable=False),
        sa.Column("commitment_date", sa.Date(), nullable=False),
        sa.Column("required_date", sa.Date(), nullable=True),
        sa.Column(
            "currency_code",
            sa.String(3),
            sa.ForeignKey("currencies.code", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("exchange_rate", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column(
            "status_code", sa.String(20), nullable=False, server_default="draft"
        ),
        sa.Column("reference_number", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "total_amount",
            sa.Numeric(precision=15, scale=2),
            nullable=False,
            server_default="0",
        ),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column(
            "approved_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "company_id",
            "commitment_number",
            name="uq_project_commitments_company_number",
        ),
    )
    op.create_index(
        "ix_project_commitments_company_project_status",
        "project_commitments",
        ["company_id", "project_id", "status_code"],
    )

    # ── project_commitment_lines ───────────────────────────────────────────────
    op.create_table(
        "project_commitment_lines",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "project_commitment_id",
            sa.Integer(),
            sa.ForeignKey("project_commitments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column(
            "project_job_id",
            sa.Integer(),
            sa.ForeignKey("project_jobs.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "project_cost_code_id",
            sa.Integer(),
            sa.ForeignKey("project_cost_codes.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("unit_rate", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("line_amount", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "project_commitment_id",
            "line_number",
            name="uq_project_commitment_lines_commitment_line",
        ),
    )
    op.create_index(
        "ix_project_commitment_lines_commitment_job",
        "project_commitment_lines",
        ["project_commitment_id", "project_job_id"],
    )


def downgrade() -> None:
    op.drop_table("project_commitment_lines")
    op.drop_table("project_commitments")
