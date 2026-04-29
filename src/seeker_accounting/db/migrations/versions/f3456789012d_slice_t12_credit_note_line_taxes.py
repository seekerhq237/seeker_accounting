"""Slice T12: credit-note line-level tax detail rows.

Closes the symmetry gap left by Slice T3 by adding line-tax detail
tables for the two credit-note families:

  * ``sales_credit_note_line_taxes``
  * ``purchase_credit_note_line_taxes``

Like the T3 tables, each row snapshots one tax-code consequence of the
parent line (taxable base, tax amount, recoverable flag for
purchases). The schema admits multiple rows per parent line so
multi-tax-per-line authoring (VAT + excise + withholding combinations)
can land without another migration.

These rows are the canonical input to the immutable PostedTaxLine
fact table (Slice T11) at posting time — credit-note posting writes
signed-negative facts so that ``SUM(tax_amount)`` over a period yields
the correct net automatically.

See ``docs/taxation_implementation_blueprint.md`` (Phase 1).

Revision ID: f3456789012d
Revises: f2345678901c
Create Date: 2026-05-15 09:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f3456789012d"
down_revision: Union[str, None] = "f2345678901c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (table_name, parent_line_table, parent_line_fk_column)
_CHILD_TABLES: tuple[tuple[str, str, str], ...] = (
    (
        "sales_credit_note_line_taxes",
        "sales_credit_note_lines",
        "sales_credit_note_line_id",
    ),
    (
        "purchase_credit_note_line_taxes",
        "purchase_credit_note_lines",
        "purchase_credit_note_line_id",
    ),
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
