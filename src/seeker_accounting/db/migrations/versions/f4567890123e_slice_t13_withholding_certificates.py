"""Slice T13: withholding tax certificates register.

Phase 5 of the taxation blueprint. Adds a standalone register for
withholding-tax events:

* **INBOUND** — certificates issued by a customer (or other paying
  party) who withheld tax on a payment due to us. The withheld tax is
  a receivable from the tax authority and may offset our own
  liabilities.

* **OUTBOUND** — certificates we issue when we withhold tax on a
  payment to a counterparty (TSR, ``précompte``, AIT, etc.). The
  amount is a liability owed to the tax authority and the certificate
  is the legal proof the supplier needs.

The register is intentionally loose about counterparty linkage and
source document linkage so reconciliation-only certificates can be
captured. Counterparty name and NIU are snapshot at row creation so
the certificate stays valid even if the underlying customer or
supplier record is later edited.

Revision ID: f4567890123e
Revises: f3456789012d
Create Date: 2026-05-16 09:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f4567890123e"
down_revision: Union[str, None] = "f3456789012d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "withholding_tax_certificates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("fiscal_period_id", sa.Integer(), nullable=True),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("counterparty_kind", sa.String(length=20), nullable=False),
        sa.Column("counterparty_id", sa.Integer(), nullable=True),
        sa.Column("counterparty_name", sa.String(length=200), nullable=False),
        sa.Column("counterparty_niu", sa.String(length=50), nullable=True),
        sa.Column("tax_code_id", sa.Integer(), nullable=False),
        sa.Column("certificate_number", sa.String(length=80), nullable=False),
        sa.Column("certificate_date", sa.Date(), nullable=False),
        sa.Column("source_document_type", sa.String(length=50), nullable=True),
        sa.Column("source_document_id", sa.Integer(), nullable=True),
        sa.Column("taxable_base", sa.Numeric(18, 2), nullable=False),
        sa.Column("tax_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("evidence_attachment_path", sa.String(length=500), nullable=True),
        sa.Column("status_code", sa.String(length=20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("recorded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["fiscal_period_id"], ["fiscal_periods.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["tax_code_id"], ["tax_codes.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_withholding_tax_certificates_company_id",
        "withholding_tax_certificates",
        ["company_id"],
    )
    op.create_index(
        "ix_withholding_tax_certificates_company_period",
        "withholding_tax_certificates",
        ["company_id", "fiscal_period_id"],
    )
    op.create_index(
        "ix_withholding_tax_certificates_company_direction",
        "withholding_tax_certificates",
        ["company_id", "direction"],
    )
    op.create_index(
        "ix_withholding_tax_certificates_tax_code_id",
        "withholding_tax_certificates",
        ["tax_code_id"],
    )
    # Per-direction uniqueness of certificate_number is enforced by the
    # service (lookup via repository) rather than a DB-level unique
    # constraint, because real-world certificate numbering can include
    # duplicates across directions and across legacy migrations.


def downgrade() -> None:
    op.drop_index(
        "ix_withholding_tax_certificates_tax_code_id",
        table_name="withholding_tax_certificates",
    )
    op.drop_index(
        "ix_withholding_tax_certificates_company_direction",
        table_name="withholding_tax_certificates",
    )
    op.drop_index(
        "ix_withholding_tax_certificates_company_period",
        table_name="withholding_tax_certificates",
    )
    op.drop_index(
        "ix_withholding_tax_certificates_company_id",
        table_name="withholding_tax_certificates",
    )
    op.drop_table("withholding_tax_certificates")
