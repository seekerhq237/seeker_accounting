"""Revision J: Fixed Assets — asset_categories, assets, asset_depreciation_runs, asset_depreciation_run_lines.

Creates the core fixed-asset accounting tables:
- asset_categories: category-level account mapping and depreciation defaults
- assets: asset register with asset-level depreciation settings
- asset_depreciation_runs: period-end depreciation run batch header
- asset_depreciation_run_lines: per-asset depreciation amounts per run

Depreciation method codes supported: straight_line | reducing_balance | sum_of_years_digits
Asset status codes: draft | active | fully_depreciated | disposed
Run status codes: draft | posted | cancelled

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-03-25
"""

from __future__ import annotations

from datetime import datetime

from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- asset_categories --
    op.create_table(
        "asset_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column(
            "asset_account_id",
            sa.Integer(),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "accumulated_depreciation_account_id",
            sa.Integer(),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "depreciation_expense_account_id",
            sa.Integer(),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("default_useful_life_months", sa.Integer(), nullable=False),
        sa.Column("default_depreciation_method_code", sa.String(30), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "code"),
    )
    op.create_index("ix_asset_categories_company_id", "asset_categories", ["company_id"])

    # -- assets --
    op.create_table(
        "assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("asset_number", sa.String(40), nullable=False),
        sa.Column("asset_name", sa.String(150), nullable=False),
        sa.Column(
            "asset_category_id",
            sa.Integer(),
            sa.ForeignKey("asset_categories.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("acquisition_date", sa.Date(), nullable=False),
        sa.Column("capitalization_date", sa.Date(), nullable=False),
        sa.Column("acquisition_cost", sa.Numeric(18, 6), nullable=False),
        sa.Column("salvage_value", sa.Numeric(18, 6), nullable=True),
        sa.Column("useful_life_months", sa.Integer(), nullable=False),
        sa.Column("depreciation_method_code", sa.String(30), nullable=False),
        sa.Column("status_code", sa.String(20), nullable=False, server_default="draft"),
        sa.Column(
            "supplier_id",
            sa.Integer(),
            sa.ForeignKey("suppliers.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "purchase_bill_id",
            sa.Integer(),
            sa.ForeignKey("purchase_bills.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "asset_number"),
    )
    op.create_index("ix_assets_company_id", "assets", ["company_id"])
    op.create_index("ix_assets_company_id_status_code", "assets", ["company_id", "status_code"])

    # -- asset_depreciation_runs --
    op.create_table(
        "asset_depreciation_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("run_number", sa.String(40), nullable=True),
        sa.Column("run_date", sa.Date(), nullable=False),
        sa.Column("period_end_date", sa.Date(), nullable=False),
        sa.Column("status_code", sa.String(20), nullable=False, server_default="draft"),
        sa.Column(
            "posted_journal_entry_id",
            sa.Integer(),
            sa.ForeignKey("journal_entries.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("posted_at", sa.DateTime(), nullable=True),
        sa.Column(
            "posted_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "run_number"),
    )
    op.create_index("ix_asset_depreciation_runs_company_id", "asset_depreciation_runs", ["company_id"])
    op.create_index(
        "ix_asset_depreciation_runs_company_id_status_code",
        "asset_depreciation_runs",
        ["company_id", "status_code"],
    )

    # -- asset_depreciation_run_lines --
    op.create_table(
        "asset_depreciation_run_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "asset_depreciation_run_id",
            sa.Integer(),
            sa.ForeignKey("asset_depreciation_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "asset_id",
            sa.Integer(),
            sa.ForeignKey("assets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("depreciation_amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("accumulated_depreciation_after", sa.Numeric(18, 6), nullable=False),
        sa.Column("net_book_value_after", sa.Numeric(18, 6), nullable=False),
    )
    op.create_index(
        "ix_asset_depreciation_run_lines_run_id",
        "asset_depreciation_run_lines",
        ["asset_depreciation_run_id"],
    )
    op.create_index(
        "ix_asset_depreciation_run_lines_asset_id",
        "asset_depreciation_run_lines",
        ["asset_id"],
    )


def downgrade() -> None:
    op.drop_table("asset_depreciation_run_lines")
    op.drop_table("asset_depreciation_runs")
    op.drop_table("assets")
    op.drop_table("asset_categories")
