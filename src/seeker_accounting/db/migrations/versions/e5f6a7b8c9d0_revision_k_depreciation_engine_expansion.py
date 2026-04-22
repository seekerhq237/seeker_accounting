"""Revision K: Depreciation Engine Expansion.

Adds the following tables to support a full built-in depreciation method catalog:
    depreciation_methods         — seeded catalog of all built-in methods with capability flags
    macrs_profiles               — seeded MACRS GDS annual rate tables
    asset_depreciation_settings  — per-asset method-specific parameters (0..1 per asset)
    asset_components             — child components for 'component' method
    asset_usage_records          — period usage for units_of_production / depletion
    asset_depreciation_pools     — group/composite pool headers
    asset_depreciation_pool_members — pool membership records
    asset_depletion_profiles     — depletion parameters for natural-resource assets

All tables are additive.  Existing Slice 12 tables and data are preserved unchanged.
Method codes added to VALID set (backward-compatible):
    straight_line, reducing_balance, sum_of_years_digits  — already in Revision J
    declining_balance, double_declining_balance, declining_balance_150
    units_of_production, component, group, composite
    depletion, annuity, sinking_fund, macrs, amortization

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-03-25
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

_DEPRECIATION_METHODS = [
    # code, name, family, req_settings, req_components, req_usage, req_pool,
    # req_depletion, has_switch_sl, sort_order
    ("straight_line",           "Straight-Line",                         "PPE",              False, False, False, False, False, False, 10),
    ("declining_balance",       "Declining Balance (1x)",                 "PPE",              True,  False, False, False, False, True,  20),
    ("double_declining_balance","Double Declining Balance",               "PPE",              True,  False, False, False, False, True,  30),
    ("declining_balance_150",   "150% Declining Balance",                 "PPE",              True,  False, False, False, False, True,  40),
    ("reducing_balance",        "Reducing Balance (DDB compat alias)",    "PPE",              True,  False, False, False, False, True,  45),
    ("sum_of_years_digits",     "Sum-of-Years-Digits",                    "PPE",              False, False, False, False, False, False, 50),
    ("units_of_production",     "Units of Production",                    "PPE",              True,  False, True,  False, False, False, 60),
    ("component",               "Component Depreciation",                 "PPE",              False, True,  False, False, False, False, 70),
    ("group",                   "Group Depreciation",                     "PPE",              False, False, False, True,  False, False, 80),
    ("composite",               "Composite Depreciation",                 "PPE",              False, False, False, True,  False, False, 90),
    ("depletion",               "Depletion (Cost Method)",                "NATURAL_RESOURCE", True,  False, True,  False, True,  False, 100),
    ("annuity",                 "Annuity Method",                         "PPE",              True,  False, False, False, False, False, 110),
    ("sinking_fund",            "Sinking Fund Method",                    "PPE",              True,  False, False, False, False, False, 120),
    ("macrs",                   "MACRS (GDS)",                            "TAX",              True,  False, False, False, False, False, 130),
    ("amortization",            "Straight-Line Amortization (Intangibles)","INTANGIBLE",      False, False, False, False, False, False, 140),
]

# MACRS GDS annual rates (%) for half-year convention (IRS Publication 946).
# Array length = recovery_period_years + 1 (extra year for half-year convention).
_MACRS_PROFILES = [
    ("3-year",  "3-Year Property (e.g. tractor units, racehorses)",  3,  "half_year",
     [33.33, 44.45, 14.81, 7.41]),
    ("5-year",  "5-Year Property (e.g. computers, cars, light trucks)", 5, "half_year",
     [20.00, 32.00, 19.20, 11.52, 11.52, 5.76]),
    ("7-year",  "7-Year Property (e.g. office furniture, most machinery)", 7, "half_year",
     [14.29, 24.49, 17.49, 12.49, 8.93, 8.92, 8.93, 4.46]),
    ("10-year", "10-Year Property (e.g. vessels, barges, tugs)", 10, "half_year",
     [10.00, 18.00, 14.40, 11.52, 9.22, 7.37, 6.55, 6.55, 6.56, 6.55, 3.28]),
    ("15-year", "15-Year Property (e.g. land improvements, retail buildings <1987)", 15, "half_year",
     [5.00, 9.50, 8.55, 7.70, 6.93, 6.23, 5.90, 5.90, 5.91, 5.90, 5.91, 5.90, 5.91, 5.90, 5.91, 2.95]),
    ("20-year", "20-Year Property (e.g. farm buildings, municipal sewers)", 20, "half_year",
     [3.750, 7.219, 6.677, 6.177, 5.713, 5.285, 4.888, 4.522, 4.462, 4.461,
      4.462, 4.461, 4.462, 4.461, 4.462, 4.461, 4.462, 4.461, 4.462, 4.461, 2.231]),
    # Mid-quarter convention — first quarter placed-in-service (Q1)
    ("7-year",  "7-Year Property — Mid-Quarter Q1", 7, "mid_quarter_q1",
     [25.00, 21.43, 15.31, 10.93, 8.75, 8.74, 8.75, 1.09]),
    # Mid-month convention — commercial real property (simplified, 39-year)
    # Stored as annual rates for 40 years (half-year last)
    ("39-year", "39-Year Nonresidential Real Property", 39, "mid_month",
     [2.461] + [2.564] * 38 + [0.107]),
]


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # depreciation_methods
    # ------------------------------------------------------------------ #
    op.create_table(
        "depreciation_methods",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("asset_family_code", sa.String(30), nullable=False),
        sa.Column("requires_settings", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("requires_components", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("requires_usage_records", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("requires_pool", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("requires_depletion_profile", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("has_switch_to_sl", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.UniqueConstraint("code"),
    )

    # ------------------------------------------------------------------ #
    # macrs_profiles
    # ------------------------------------------------------------------ #
    op.create_table(
        "macrs_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("class_code", sa.String(20), nullable=False),
        sa.Column("class_name", sa.String(100), nullable=False),
        sa.Column("recovery_period_years", sa.Integer(), nullable=False),
        sa.Column("convention_code", sa.String(20), nullable=False),
        sa.Column("gds_rates_json", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.UniqueConstraint("class_code", "convention_code"),
    )

    # ------------------------------------------------------------------ #
    # asset_depreciation_settings
    # ------------------------------------------------------------------ #
    op.create_table(
        "asset_depreciation_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "asset_id",
            sa.Integer(),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("declining_factor", sa.Numeric(5, 2), nullable=True),
        sa.Column("switch_to_straight_line", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("expected_total_units", sa.Numeric(18, 4), nullable=True),
        sa.Column("interest_rate", sa.Numeric(10, 8), nullable=True),
        sa.Column(
            "macrs_profile_id",
            sa.Integer(),
            sa.ForeignKey("macrs_profiles.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("macrs_convention_code", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("asset_id"),
    )
    op.create_index(
        "ix_asset_depreciation_settings_company_id",
        "asset_depreciation_settings",
        ["company_id"],
    )

    # ------------------------------------------------------------------ #
    # asset_components
    # ------------------------------------------------------------------ #
    op.create_table(
        "asset_components",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "parent_asset_id",
            sa.Integer(),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("component_name", sa.String(150), nullable=False),
        sa.Column("acquisition_cost", sa.Numeric(18, 6), nullable=False),
        sa.Column("salvage_value", sa.Numeric(18, 6), nullable=True),
        sa.Column("useful_life_months", sa.Integer(), nullable=False),
        sa.Column("depreciation_method_code", sa.String(30), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_asset_components_parent_asset_id", "asset_components", ["parent_asset_id"])
    op.create_index("ix_asset_components_company_id", "asset_components", ["company_id"])

    # ------------------------------------------------------------------ #
    # asset_usage_records
    # ------------------------------------------------------------------ #
    op.create_table(
        "asset_usage_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "asset_id",
            sa.Integer(),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("units_used", sa.Numeric(18, 4), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_asset_usage_records_asset_id", "asset_usage_records", ["asset_id"])
    op.create_index("ix_asset_usage_records_company_id", "asset_usage_records", ["company_id"])

    # ------------------------------------------------------------------ #
    # asset_depreciation_pools
    # ------------------------------------------------------------------ #
    op.create_table(
        "asset_depreciation_pools",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("pool_type_code", sa.String(20), nullable=False),
        sa.Column("depreciation_method_code", sa.String(30), nullable=False),
        sa.Column("useful_life_months", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "code"),
    )
    op.create_index("ix_asset_depreciation_pools_company_id", "asset_depreciation_pools", ["company_id"])

    # ------------------------------------------------------------------ #
    # asset_depreciation_pool_members
    # ------------------------------------------------------------------ #
    op.create_table(
        "asset_depreciation_pool_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "pool_id",
            sa.Integer(),
            sa.ForeignKey("asset_depreciation_pools.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "asset_id",
            sa.Integer(),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("joined_date", sa.Date(), nullable=False),
        sa.Column("left_date", sa.Date(), nullable=True),
        sa.UniqueConstraint("pool_id", "asset_id"),
    )
    op.create_index("ix_asset_depr_pool_members_pool_id", "asset_depreciation_pool_members", ["pool_id"])
    op.create_index("ix_asset_depr_pool_members_asset_id", "asset_depreciation_pool_members", ["asset_id"])

    # ------------------------------------------------------------------ #
    # asset_depletion_profiles
    # ------------------------------------------------------------------ #
    op.create_table(
        "asset_depletion_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "asset_id",
            sa.Integer(),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("estimated_total_units", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_description", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("asset_id"),
    )
    op.create_index("ix_asset_depletion_profiles_company_id", "asset_depletion_profiles", ["company_id"])

    # ------------------------------------------------------------------ #
    # Seed: depreciation_methods
    # ------------------------------------------------------------------ #
    dep_methods_table = sa.table(
        "depreciation_methods",
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("asset_family_code", sa.String),
        sa.column("requires_settings", sa.Boolean),
        sa.column("requires_components", sa.Boolean),
        sa.column("requires_usage_records", sa.Boolean),
        sa.column("requires_pool", sa.Boolean),
        sa.column("requires_depletion_profile", sa.Boolean),
        sa.column("has_switch_to_sl", sa.Boolean),
        sa.column("sort_order", sa.Integer),
        sa.column("is_active", sa.Boolean),
    )
    op.bulk_insert(
        dep_methods_table,
        [
            {
                "code": row[0], "name": row[1], "asset_family_code": row[2],
                "requires_settings": row[3], "requires_components": row[4],
                "requires_usage_records": row[5], "requires_pool": row[6],
                "requires_depletion_profile": row[7], "has_switch_to_sl": row[8],
                "sort_order": row[9], "is_active": True,
            }
            for row in _DEPRECIATION_METHODS
        ],
    )

    # ------------------------------------------------------------------ #
    # Seed: macrs_profiles
    # ------------------------------------------------------------------ #
    macrs_table = sa.table(
        "macrs_profiles",
        sa.column("class_code", sa.String),
        sa.column("class_name", sa.String),
        sa.column("recovery_period_years", sa.Integer),
        sa.column("convention_code", sa.String),
        sa.column("gds_rates_json", sa.Text),
        sa.column("is_active", sa.Boolean),
    )
    op.bulk_insert(
        macrs_table,
        [
            {
                "class_code": row[0],
                "class_name": row[1],
                "recovery_period_years": row[2],
                "convention_code": row[3],
                "gds_rates_json": json.dumps(row[4]),
                "is_active": True,
            }
            for row in _MACRS_PROFILES
        ],
    )


def downgrade() -> None:
    op.drop_table("asset_depletion_profiles")
    op.drop_table("asset_depreciation_pool_members")
    op.drop_table("asset_depreciation_pools")
    op.drop_table("asset_usage_records")
    op.drop_table("asset_components")
    op.drop_table("asset_depreciation_settings")
    op.drop_table("macrs_profiles")
    op.drop_table("depreciation_methods")
