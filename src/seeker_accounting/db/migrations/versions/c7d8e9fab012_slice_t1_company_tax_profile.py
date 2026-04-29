"""Slice T1: company tax profile.

Adds the ``company_tax_profiles`` table — one row per company, holding
the tax-compliance identity used by VAT, CIT, DSF and filing workflows.

See ``docs/taxation_implementation_blueprint.md`` (Phase 1 / VAT MVP).

Revision ID: c7d8e9fab012
Revises: b5c6d7e8f9a0
Create Date: 2026-04-28 11:30:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c7d8e9fab012"
down_revision: Union[str, None] = "b5c6d7e8f9a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "company_tax_profiles",
        sa.Column("company_id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("niu", sa.String(length=50), nullable=True),
        sa.Column("tax_center_code", sa.String(length=50), nullable=True),
        sa.Column("taxpayer_segment_code", sa.String(length=50), nullable=True),
        sa.Column("tax_regime_code", sa.String(length=50), nullable=True),
        sa.Column(
            "is_vat_liable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("vat_effective_from", sa.Date(), nullable=True),
        sa.Column("cit_rate_profile_code", sa.String(length=50), nullable=True),
        sa.Column("cit_installment_profile_code", sa.String(length=50), nullable=True),
        sa.Column(
            "sme_qualified_flag",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("dsf_form_code", sa.String(length=50), nullable=True),
        sa.Column("dsf_submission_mode_code", sa.String(length=50), nullable=True),
        sa.Column(
            "otp_enabled_flag",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "default_withholding_applicable_flag",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            ondelete="RESTRICT",
            name="fk_company_tax_profiles_company_id_companies",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_company_tax_profiles_updated_by_user_id_users",
        ),
    )


def downgrade() -> None:
    op.drop_table("company_tax_profiles")
