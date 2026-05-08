"""P1 performance indexes

Revision ID: a14b00000026
Revises: a14b00000025
Create Date: 2025-01-01 00:00:00.000000

"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "a14b00000026"
down_revision = "a14b00000025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Most composite indexes on customers, journal_entries, and payroll_runs already
    # exist in the database from model-level Index declarations applied outside of
    # migrations. Only the suppliers composite index was missing.
    with op.batch_alter_table("suppliers") as batch_op:
        batch_op.create_index("ix_suppliers_company_id_is_active", ["company_id", "is_active"])


def downgrade() -> None:
    with op.batch_alter_table("suppliers") as batch_op:
        batch_op.drop_index("ix_suppliers_company_id_is_active")
