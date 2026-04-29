"""DTOs for journal reversal."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class ReverseJournalCommand:
    reversal_date: date
    reason: str
    auto_post: bool = True


@dataclass(frozen=True, slots=True)
class JournalReversalResultDTO:
    source_journal_entry_id: int
    source_entry_number: str
    reversal_journal_entry_id: int
    reversal_entry_number: str
    reversal_date: date
    line_count: int
    auto_posted: bool
    posted_at: datetime | None
