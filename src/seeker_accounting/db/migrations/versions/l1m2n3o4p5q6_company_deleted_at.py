"""Add deleted_at column to companies table.

Revision ID: l1m2n3o4p5q6
Revises: k4l5m6n7o8p9
Create Date: 2026-03-30

Changes:
- Add nullable deleted_at (DATETIME) column to companies table.
  Used to track when a company was scheduled for permanent deletion.
  Semantics:
    is_active=True,  deleted_at=None          -> Active
    is_active=False, deleted_at=None          -> Deactivated
    is_active=False, deleted_at IS NOT NULL   -> Pending Deletion (purge after 30 days)
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "l1m2n3o4p5q6"
down_revision = "k4l5m6n7o8p9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("deleted_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("companies") as batch_op:
        batch_op.drop_column("deleted_at")
