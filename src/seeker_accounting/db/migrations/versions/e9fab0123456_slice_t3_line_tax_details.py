"""Slice T3: line-level tax detail rows.

Adds five child tables — one per document type that carries tax
amounts — that store per-tax-code breakdown for each transaction
line:

  * ``sales_invoice_line_taxes``
  * ``sales_order_line_taxes``
  * ``customer_quote_line_taxes``
  * ``purchase_order_line_taxes``
  * ``purchase_bill_line_taxes``

The schema admits multiple rows per parent line so multi-tax-per-line
authoring can land in a follow-up without another migration. Today the
services write one row per line, mirroring the legacy single-tax
shape. ``is_recoverable`` is captured at row-creation time for
purchases (where it drives non-deductible VAT routing) and is null on
sales rows.

See ``docs/taxation_implementation_blueprint.md`` (Phase 1, item 4 of
the recommended first backlog).

Revision ID: e9fab0123456
Revises: d8e9fab01234
Create Date: 2026-04-28 13:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e9fab0123456"
down_revision: Union[str, None] = "d8e9fab01234"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (table_name, parent_line_table, parent_line_fk_column)
_CHILD_TABLES: tuple[tuple[str, str, str], ...] = (
    ("sales_invoice_line_taxes", "sales_invoice_lines", "sales_invoice_line_id"),
    ("sales_order_line_taxes", "sales_order_lines", "sales_order_line_id"),
    ("customer_quote_line_taxes", "customer_quote_lines", "customer_quote_line_id"),
    ("purchase_order_line_taxes", "purchase_order_lines", "purchase_order_line_id"),
    ("purchase_bill_line_taxes", "purchase_bill_lines", "purchase_bill_line_id"),
)


def upgrade() -> None:
    for table_name, parent_table, fk_column in _CHILD_TABLES:
        op.create_table(
            table_name,
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column(fk_column, sa.Integer(), nullable=False),
            sa.Column("tax_code_id", sa.Integer(), nullable=True),
            sa.Column("taxable_base", sa.Numeric(18, 2), nullable=False),
            sa.Column("tax_amount", sa.Numeric(18, 2), nullable=False),
            sa.Column("is_recoverable", sa.Boolean(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(
                [fk_column],
                [f"{parent_table}.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["tax_code_id"],
                ["tax_codes.id"],
                ondelete="RESTRICT",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            f"ix_{table_name}_line_id",
            table_name,
            [fk_column],
        )
        op.create_index(
            f"ix_{table_name}_tax_code_id",
            table_name,
            ["tax_code_id"],
        )


def downgrade() -> None:
    for table_name, _parent_table, _fk_column in reversed(_CHILD_TABLES):
        op.drop_index(f"ix_{table_name}_tax_code_id", table_name=table_name)
        op.drop_index(f"ix_{table_name}_line_id", table_name=table_name)
        op.drop_table(table_name)
