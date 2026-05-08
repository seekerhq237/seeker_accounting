"""Create payroll authority remittance mapping tables.

Revision ID: a14b00000027
Revises: a14b00000026
Create Date: 2026-05-07 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a14b00000027"
down_revision = "a14b00000026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payroll_authorities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("jurisdiction_code", sa.String(length=10), nullable=True),
        sa.Column(
            "filing_cadence_code",
            sa.String(length=20),
            nullable=False,
            server_default="monthly",
        ),
        sa.Column("deadline_rule_code", sa.String(length=40), nullable=True),
        sa.Column("deadline_day", sa.Integer(), nullable=True),
        sa.Column("gl_liability_account_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["gl_liability_account_id"], ["accounts.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("company_id", "code", name="uq_payroll_authorities_company_code"),
    )
    op.create_index(
        "ix_payroll_authorities_company_id", "payroll_authorities", ["company_id"]
    )

    op.create_table(
        "payroll_component_authority_map",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("component_id", sa.Integer(), nullable=False),
        sa.Column("authority_id", sa.Integer(), nullable=False),
        sa.Column("side", sa.String(length=20), nullable=False, server_default="total"),
        sa.Column(
            "line_kind",
            sa.String(length=30),
            nullable=False,
            server_default="contribution",
        ),
        sa.Column("fraction", sa.Numeric(10, 6), nullable=False, server_default="1.0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["component_id"], ["payroll_components.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["authority_id"], ["payroll_authorities.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "company_id",
            "component_id",
            "authority_id",
            "side",
            name="uq_payroll_component_authority_map",
        ),
    )
    op.create_index(
        "ix_payroll_component_authority_map_company_id",
        "payroll_component_authority_map",
        ["company_id"],
    )
    op.create_index(
        "ix_payroll_component_authority_map_authority_id",
        "payroll_component_authority_map",
        ["authority_id"],
    )
    op.create_index(
        "ix_payroll_component_authority_map_component_id",
        "payroll_component_authority_map",
        ["component_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_payroll_component_authority_map_component_id",
        table_name="payroll_component_authority_map",
    )
    op.drop_index(
        "ix_payroll_component_authority_map_authority_id",
        table_name="payroll_component_authority_map",
    )
    op.drop_index(
        "ix_payroll_component_authority_map_company_id",
        table_name="payroll_component_authority_map",
    )
    op.drop_table("payroll_component_authority_map")
    op.drop_index("ix_payroll_authorities_company_id", table_name="payroll_authorities")
    op.drop_table("payroll_authorities")
