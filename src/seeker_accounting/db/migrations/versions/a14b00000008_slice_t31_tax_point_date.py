"""Slice T31: tax_point_date as first-class field on documents and posted facts.

Revision ID: a14b00000008
Revises: p4s1_emp_onboarding
Create Date: 2026-05-01

Additive nullable columns:

* ``sales_invoices.tax_point_date``
* ``sales_credit_notes.tax_point_date``
* ``purchase_bills.tax_point_date``
* ``purchase_credit_notes.tax_point_date``
* ``posted_tax_lines.tax_point_date``
* ``company_tax_profiles.vat_uses_tax_point`` (BOOL NOT NULL DEFAULT FALSE)

When ``tax_point_date`` is NULL on a source document, the posting
service falls back to the document date (invoice_date / credit_date /
bill_date). The fact-table column is *non-null at insert time* once
T31 is live (posting service always derives a value), but the column
itself stays nullable for forward-compat with pre-T31 historical rows.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a14b00000008"
down_revision: Union[str, None] = "p4s1_emp_onboarding"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("sales_invoices") as batch_op:
        batch_op.add_column(sa.Column("tax_point_date", sa.Date(), nullable=True))

    with op.batch_alter_table("sales_credit_notes") as batch_op:
        batch_op.add_column(sa.Column("tax_point_date", sa.Date(), nullable=True))

    with op.batch_alter_table("purchase_bills") as batch_op:
        batch_op.add_column(sa.Column("tax_point_date", sa.Date(), nullable=True))

    with op.batch_alter_table("purchase_credit_notes") as batch_op:
        batch_op.add_column(sa.Column("tax_point_date", sa.Date(), nullable=True))

    with op.batch_alter_table("posted_tax_lines") as batch_op:
        batch_op.add_column(sa.Column("tax_point_date", sa.Date(), nullable=True))
        batch_op.create_index(
            "ix_posted_tax_lines_company_tax_point_date",
            ["company_id", "tax_point_date"],
        )

    with op.batch_alter_table("company_tax_profiles") as batch_op:
        batch_op.add_column(
            sa.Column(
                "vat_uses_tax_point",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("company_tax_profiles") as batch_op:
        batch_op.drop_column("vat_uses_tax_point")

    with op.batch_alter_table("posted_tax_lines") as batch_op:
        batch_op.drop_index("ix_posted_tax_lines_company_tax_point_date")
        batch_op.drop_column("tax_point_date")

    with op.batch_alter_table("purchase_credit_notes") as batch_op:
        batch_op.drop_column("tax_point_date")

    with op.batch_alter_table("purchase_bills") as batch_op:
        batch_op.drop_column("tax_point_date")

    with op.batch_alter_table("sales_credit_notes") as batch_op:
        batch_op.drop_column("tax_point_date")

    with op.batch_alter_table("sales_invoices") as batch_op:
        batch_op.drop_column("tax_point_date")
