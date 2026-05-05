"""T38-T42: capital-goods register, customer withholds-VAT flag,
and late-claim rollover column.

T38: Add ``vat_capital_goods_register`` table for multi-year VAT
     capital-goods adjustment tracking.
T37 (deferral): Add ``customers.withholds_vat`` boolean flag.
T42: Add ``posted_tax_lines.included_in_return_id`` FK to track which
     VAT return first claimed a given PostedTaxLine fact (enables
     late-claim rollover in subsequent periods).

Revision ID: a14b00000014
Revises: a14b00000013
Create Date: 2026-05-15 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a14b00000014"
down_revision = "a14b00000013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── vat_capital_goods_register (T38) ─────────────────────────────
    op.create_table(
        "vat_capital_goods_register",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        # Nullable FK to future fixed_assets table.
        sa.Column("fixed_asset_id", sa.Integer(), nullable=True),
        sa.Column("asset_description", sa.String(200), nullable=False),
        sa.Column("acquisition_date", sa.Date(), nullable=False),
        sa.Column("base_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column(
            "vat_recovered_initial",
            sa.Numeric(18, 2),
            nullable=False,
            server_default="0.00",
        ),
        sa.Column(
            "monitored_years",
            sa.Integer(),
            nullable=False,
            server_default="5",
        ),
        sa.Column(
            "status_code",
            sa.String(20),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column("disposal_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_vat_cg_company_id", "vat_capital_goods_register", ["company_id"]
    )

    # ── customers.withholds_vat (T37 deferral) ───────────────────────
    with op.batch_alter_table("customers") as batch:
        batch.add_column(
            sa.Column(
                "withholds_vat",
                sa.Boolean(),
                nullable=False,
                server_default="0",
            )
        )

    # ── posted_tax_lines.included_in_return_id (T42) ─────────────────
    with op.batch_alter_table("posted_tax_lines") as batch:
        batch.add_column(
            sa.Column(
                "included_in_return_id",
                sa.Integer(),
                sa.ForeignKey("tax_returns.id", ondelete="SET NULL"),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("posted_tax_lines") as batch:
        batch.drop_column("included_in_return_id")

    with op.batch_alter_table("customers") as batch:
        batch.drop_column("withholds_vat")

    op.drop_index("ix_vat_cg_company_id", table_name="vat_capital_goods_register")
    op.drop_table("vat_capital_goods_register")
