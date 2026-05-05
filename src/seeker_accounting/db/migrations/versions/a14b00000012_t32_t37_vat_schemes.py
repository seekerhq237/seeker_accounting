"""T32-T37: cash-basis VAT, reverse-charge, pro-rata, amendments,
credit carry-forward, and withholding VAT (précompte).

Revision ID: a14b00000012
Revises: a14b00000011
Create Date: 2026-05-01 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a14b00000012"
down_revision = "a14b00000011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── company_tax_profiles ─────────────────────────────────────────
    # T32: VAT accounting basis (ACCRUAL / CASH).
    # T34: pro-rata percentage for mixed-supply companies.
    with op.batch_alter_table("company_tax_profiles") as batch:
        batch.add_column(
            sa.Column(
                "vat_accounting_basis",
                sa.String(20),
                nullable=False,
                server_default="ACCRUAL",
            )
        )
        batch.add_column(
            sa.Column(
                "vat_pro_rata_percent",
                sa.Numeric(5, 2),
                nullable=True,
            )
        )

    # ── tax_codes ───────────────────────────────────────────────────
    # T33: mark a tax code as reverse-charge so the posting service
    # writes both an output and an input fact row.
    with op.batch_alter_table("tax_codes") as batch:
        batch.add_column(
            sa.Column(
                "is_reverse_charge",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )

    # ── posted_tax_lines ────────────────────────────────────────────
    # T32: payment_date — set when an invoice is allocated against a
    #      receipt; used to filter facts in cash-basis VAT returns.
    # T33: is_reverse_charge snapshot so the form can route correctly
    #      even if the tax code's flag changes later.
    with op.batch_alter_table("posted_tax_lines") as batch:
        batch.add_column(
            sa.Column("payment_date", sa.Date(), nullable=True)
        )
        batch.add_column(
            sa.Column(
                "is_reverse_charge",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
    op.create_index(
        "ix_posted_tax_lines_company_payment_date",
        "posted_tax_lines",
        ["company_id", "payment_date"],
    )

    # ── tax_returns ─────────────────────────────────────────────────
    # T35: amendment support — link an amended return to the original.
    # T36: credit carried forward from prior settlement.
    # T37: VAT withheld at source (précompte) received from customers.
    with op.batch_alter_table("tax_returns") as batch:
        batch.add_column(
            sa.Column(
                "is_amended",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch.add_column(
            sa.Column(
                "amends_return_id",
                sa.Integer(),
                sa.ForeignKey("tax_returns.id", ondelete="RESTRICT"),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column(
                "credit_brought_forward",
                sa.Numeric(18, 2),
                nullable=False,
                server_default="0.00",
            )
        )
        batch.add_column(
            sa.Column(
                "withholding_vat_amount",
                sa.Numeric(18, 2),
                nullable=False,
                server_default="0.00",
            )
        )

    # ── sales_invoices ──────────────────────────────────────────────
    # T37: record the VAT amount withheld at source by the customer
    #      (précompte) so the seller can claim the L45 deduction on
    #      the VAT return.
    with op.batch_alter_table("sales_invoices") as batch:
        batch.add_column(
            sa.Column(
                "withheld_vat_amount",
                sa.Numeric(18, 2),
                nullable=False,
                server_default="0.00",
            )
        )


def downgrade() -> None:
    op.drop_index(
        "ix_posted_tax_lines_company_payment_date", table_name="posted_tax_lines"
    )
    with op.batch_alter_table("posted_tax_lines") as batch:
        batch.drop_column("is_reverse_charge")
        batch.drop_column("payment_date")

    with op.batch_alter_table("tax_codes") as batch:
        batch.drop_column("is_reverse_charge")

    with op.batch_alter_table("company_tax_profiles") as batch:
        batch.drop_column("vat_pro_rata_percent")
        batch.drop_column("vat_accounting_basis")

    with op.batch_alter_table("tax_returns") as batch:
        batch.drop_column("withholding_vat_amount")
        batch.drop_column("credit_brought_forward")
        batch.drop_column("amends_return_id")
        batch.drop_column("is_amended")

    with op.batch_alter_table("sales_invoices") as batch:
        batch.drop_column("withheld_vat_amount")
