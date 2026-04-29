"""Slice T2: is_tax_inclusive document header flag.

Adds a boolean ``is_tax_inclusive`` column to all five operational
document headers (sales invoices/orders/customer quotes, purchase
orders/bills). Defaults to false so existing rows continue to behave
as tax-exclusive — preserving full backward compatibility for
in-flight documents.

See ``docs/taxation_implementation_blueprint.md`` (Phase 1, item 3 of
the recommended first backlog).

Revision ID: d8e9fab01234
Revises: c7d8e9fab012
Create Date: 2026-04-28 12:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d8e9fab01234"
down_revision: Union[str, None] = "c7d8e9fab012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TARGET_TABLES: tuple[str, ...] = (
    "sales_invoices",
    "sales_orders",
    "customer_quotes",
    "purchase_orders",
    "purchase_bills",
)


def upgrade() -> None:
    for table_name in _TARGET_TABLES:
        with op.batch_alter_table(table_name) as batch:
            batch.add_column(
                sa.Column(
                    "is_tax_inclusive",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                )
            )


def downgrade() -> None:
    for table_name in reversed(_TARGET_TABLES):
        with op.batch_alter_table(table_name) as batch:
            batch.drop_column("is_tax_inclusive")
