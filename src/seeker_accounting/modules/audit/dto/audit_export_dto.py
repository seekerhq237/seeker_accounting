"""DTOs for the audit export workflow."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path


@dataclass(frozen=True)
class AuditExportPreviewDTO:
    """Read-only counts surfaced before the export is written to disk."""

    company_id: int
    from_date: date
    to_date: date
    posted_journal_entry_count: int
    posted_journal_line_count: int
    audit_event_count: int
    include_audit_events: bool


@dataclass(frozen=True)
class AuditExportFileDTO:
    """One file produced by the export."""

    relative_name: str
    absolute_path: str
    row_count: int
    byte_size: int


@dataclass(frozen=True)
class AuditExportResultDTO:
    """Summary returned after a successful export."""

    company_id: int
    from_date: date
    to_date: date
    output_directory: str
    exported_at: datetime
    files: tuple[AuditExportFileDTO, ...] = field(default_factory=tuple)
    posted_journal_entry_count: int = 0
    posted_journal_line_count: int = 0
    audit_event_count: int = 0

    @property
    def output_path(self) -> Path:
        return Path(self.output_directory)
