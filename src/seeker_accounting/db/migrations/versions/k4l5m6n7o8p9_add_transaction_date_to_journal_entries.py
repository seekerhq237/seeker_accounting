"""Add transaction_date column to journal_entries.

Revision ID: k4l5m6n7o8p9
Revises: j3k4l5m6n7o8
Create Date: 2026-04-01

Changes:
- Add nullable transaction_date (DATE) column to journal_entries table.
  Represents the date the actual business transaction occurred, separate
  from the accounting entry_date used for fiscal period resolution.
"""

from alembic import op
import sqlalchemy as sa

revision = "k4l5m6n7o8p9"
down_revision = "j3k4l5m6n7o8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("journal_entries", sa.Column("transaction_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("journal_entries", "transaction_date")
