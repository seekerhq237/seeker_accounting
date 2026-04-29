"""Asset disposal columns.

Adds disposal-related columns to the ``assets`` table to support the
Asset Disposal workflow:

  * ``disposal_date``             â€” date the asset was disposed
  * ``disposal_amount``           â€” cash/proceeds received
  * ``disposal_reference``        â€” free-text reference (sale doc, scrap report, etc.)
  * ``disposal_journal_entry_id`` â€” FK to the journal entry that booked the disposal

See blueprint: AssetDisposalService posts a single balanced journal entry that:
  DR cash/receivable (proceeds), DR accumulated_depreciation, CR asset_cost,
  DR/CR gain_loss plug. Asset.status_code -> "disposed".

Revision ID: f1234567890b
Revises: f0123456789a
Create Date: 2026-05-12 09:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f1234567890b"
down_revision = "f0123456789a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("assets") as batch_op:
        batch_op.add_column(sa.Column("disposal_date", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("disposal_amount", sa.Numeric(18, 6), nullable=True))
        batch_op.add_column(sa.Column("disposal_reference", sa.String(length=120), nullable=True))
        batch_op.add_column(
            sa.Column("disposal_journal_entry_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_assets_disposal_journal_entry_id_journal_entries",
            "journal_entries",
            ["disposal_journal_entry_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("assets") as batch_op:
        batch_op.drop_constraint(
            "fk_assets_disposal_journal_entry_id_journal_entries",
            type_="foreignkey",
        )
        batch_op.drop_column("disposal_journal_entry_id")
        batch_op.drop_column("disposal_reference")
        batch_op.drop_column("disposal_amount")
        batch_op.drop_column("disposal_date")
