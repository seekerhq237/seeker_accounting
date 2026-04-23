"""Performance: reverse-lookup index on journal_entries(source_*).

Operational documents (customer invoices, supplier invoices, treasury
transfers, payroll runs, depreciation runs, credit notes) that have been
posted to the GL need to be reverse-mapped back to their journal entry,
for example when showing a document's posted status or audit trail.

Without an index, each such lookup scans the journal_entries table. This
migration adds a compound index covering the (source_module_code,
source_document_type, source_document_id) triple that the lookup filters on.

Revision ID: a4b5c6d7e8f9
Revises: z3a4b5c6d7e8
Create Date: 2026-04-23 10:30:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "a4b5c6d7e8f9"
down_revision: Union[str, None] = "z3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_INDEX_NAME = "ix_journal_entries_source_document"
_TABLE_NAME = "journal_entries"


def upgrade() -> None:
    op.create_index(
        _INDEX_NAME,
        _TABLE_NAME,
        ["source_module_code", "source_document_type", "source_document_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(_INDEX_NAME, table_name=_TABLE_NAME)
