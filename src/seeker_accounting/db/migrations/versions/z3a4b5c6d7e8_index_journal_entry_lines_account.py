"""Performance: add covering index for GL/Trial Balance queries on journal_entry_lines.

Rationale:
Reporting workflows (GL listing, Trial Balance, account drill-downs) filter
journal_entry_lines on account_id and join to journal_entries. Without a
matching index, SQLite performs a full scan of journal_entry_lines, which
degrades linearly with posted volume.

This migration adds a compound index (account_id, journal_entry_id) that:
- satisfies account-scoped filtering, and
- covers the join back to journal_entries through journal_entry_id.

Revision ID: z3a4b5c6d7e8
Revises: y2z3a4b5c6d7
Create Date: 2026-04-23 10:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "z3a4b5c6d7e8"
down_revision: Union[str, None] = "y2z3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_INDEX_NAME = "ix_journal_entry_lines_account_id_entry"
_TABLE_NAME = "journal_entry_lines"


def upgrade() -> None:
    op.create_index(
        _INDEX_NAME,
        _TABLE_NAME,
        ["account_id", "journal_entry_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(_INDEX_NAME, table_name=_TABLE_NAME)
