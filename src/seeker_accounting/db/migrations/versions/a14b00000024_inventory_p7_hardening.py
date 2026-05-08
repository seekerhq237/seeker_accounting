"""Inventory P7 — Hardening & migration (Slice 8.1).

Adds two schema changes required for concurrency safety and constraint
integrity:

1. ``inventory_documents.version`` (INTEGER, NOT NULL, DEFAULT 0) — optimistic-
   concurrency token.  The service layer reads this value on load and passes it
   back on save; a mismatch aborts the write.  SQLite is a single-writer so the
   constraint is enforced at the application level; PostgreSQL/Firebird can
   enforce it at the DB level using the version column in a WHERE clause.

2. ``CHECK (quantity >= 0)`` on ``stock_ledger_balances.quantity`` — belt-and-
   suspenders guard so that a bug in the ledger writer cannot produce a negative
   physical balance row.  SQLite enforces CHECK constraints as of version 3.25
   (2018); PostgreSQL and Firebird both honour them natively.

Revision ID: a14b00000024
Revises: a14b00000023
Create Date: 2026-05-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a14b00000024"
down_revision = "a14b00000023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. inventory_documents.version — optimistic-concurrency token
    # ------------------------------------------------------------------
    with op.batch_alter_table("inventory_documents") as batch_op:
        batch_op.add_column(
            sa.Column(
                "version",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )

    # ------------------------------------------------------------------
    # 2. stock_ledger_balances.quantity — non-negative CHECK constraint
    # ------------------------------------------------------------------
    with op.batch_alter_table("stock_ledger_balances") as batch_op:
        batch_op.create_check_constraint(
            "ck_slb_quantity_nonneg",
            "quantity >= 0",
        )


def downgrade() -> None:
    # Drop the CHECK constraint (batch_alter_table recreates the table on
    # SQLite; constraint is simply absent in the recreated table).
    with op.batch_alter_table("stock_ledger_balances") as batch_op:
        batch_op.drop_constraint("ck_slb_quantity_nonneg", type_="check")

    with op.batch_alter_table("inventory_documents") as batch_op:
        batch_op.drop_column("version")
