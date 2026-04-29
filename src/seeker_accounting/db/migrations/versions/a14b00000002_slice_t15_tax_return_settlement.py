"""Slice T15: tax_return settlement journal entry link.

A filed VAT return is a statement of obligation, not yet an accounting
event.  Cameroon VAT settlement transfers the period's output VAT
(443x — État, TVA facturée) and recoverable input VAT (445x — État,
TVA récupérable) into a single payable balance (4441 — État, TVA due)
or a credit carry-forward (4449 — État, crédit de TVA à reporter).

This slice introduces the link between a filed return and the journal
entry that books the settlement.  The migration is purely additive:

* ``tax_returns.journal_entry_id`` — nullable FK to the settlement JE.
* ``tax_returns.settled_at`` — timestamp the settlement JE was posted.

Returns can be filed without being settled (the return survives if
the closing-period is locked, settlement happens once the period
opens or the journal date is moved).  Settling a return without
filing it first is rejected at the service layer.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a14b00000002"
down_revision: Union[str, None] = "a14b00000001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("tax_returns") as batch:
        batch.add_column(
            sa.Column("journal_entry_id", sa.Integer(), nullable=True)
        )
        batch.add_column(
            sa.Column("settled_at", sa.DateTime(), nullable=True)
        )
        batch.create_foreign_key(
            "fk_tax_returns_journal_entry_id",
            "journal_entries",
            ["journal_entry_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_index(
            "ix_tax_returns_journal_entry_id",
            ["journal_entry_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("tax_returns") as batch:
        batch.drop_index("ix_tax_returns_journal_entry_id")
        batch.drop_constraint("fk_tax_returns_journal_entry_id", type_="foreignkey")
        batch.drop_column("settled_at")
        batch.drop_column("journal_entry_id")
