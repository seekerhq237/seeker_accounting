"""AuditExportService — package posted accounting truth and audit events
for handover to an external auditor.

This service is read-only. It does not commit, does not post journals, and
does not record audit events of its own. It produces a self-contained CSV
package on disk plus a JSON manifest describing what was included.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.accounting.journals.repositories.journal_entry_repository import (
    JournalEntryRepository,
)
from seeker_accounting.modules.audit.dto.audit_export_dto import (
    AuditExportFileDTO,
    AuditExportPreviewDTO,
    AuditExportResultDTO,
)
from seeker_accounting.modules.audit.repositories.audit_event_repository import (
    AuditEventRepository,
)
from seeker_accounting.platform.exceptions import ValidationError

JournalEntryRepositoryFactory = Callable[[Session], JournalEntryRepository]
AuditEventRepositoryFactory = Callable[[Session], AuditEventRepository]

_AUDIT_PAGE_SIZE = 1000


class AuditExportService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        journal_entry_repository_factory: JournalEntryRepositoryFactory,
        audit_event_repository_factory: AuditEventRepositoryFactory,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._je_repo_factory = journal_entry_repository_factory
        self._audit_repo_factory = audit_event_repository_factory

    # ------------------------------------------------------------------ #
    # Public API                                                          #
    # ------------------------------------------------------------------ #

    def preview(
        self,
        company_id: int,
        from_date: date,
        to_date: date,
        *,
        include_audit_events: bool = True,
    ) -> AuditExportPreviewDTO:
        self._validate_date_range(from_date, to_date)
        with self._uow_factory() as uow:
            entries = self._je_repo_factory(uow.session).list_posted_between(
                company_id, from_date, to_date
            )
            line_count = sum(len(e.lines) for e in entries)
            event_count = 0
            if include_audit_events:
                event_count = self._audit_repo_factory(uow.session).count_by_company(
                    company_id,
                    from_date=_start_of_day(from_date),
                    to_date=_end_of_day(to_date),
                )
            return AuditExportPreviewDTO(
                company_id=company_id,
                from_date=from_date,
                to_date=to_date,
                posted_journal_entry_count=len(entries),
                posted_journal_line_count=line_count,
                audit_event_count=event_count,
                include_audit_events=include_audit_events,
            )

    def export(
        self,
        company_id: int,
        from_date: date,
        to_date: date,
        output_directory: str | os.PathLike[str],
        *,
        include_audit_events: bool = True,
    ) -> AuditExportResultDTO:
        self._validate_date_range(from_date, to_date)
        out_dir = Path(output_directory)
        if not out_dir.exists():
            out_dir.mkdir(parents=True, exist_ok=True)
        if not out_dir.is_dir():
            raise ValidationError(
                f"Output path is not a directory: {out_dir}"
            )

        files: list[AuditExportFileDTO] = []
        je_count = 0
        line_count = 0
        event_count = 0

        with self._uow_factory() as uow:
            entries = self._je_repo_factory(uow.session).list_posted_between(
                company_id, from_date, to_date
            )
            je_count = len(entries)

            je_file, je_lines_file, written_lines = self._write_journal_entries(
                out_dir, entries
            )
            line_count = written_lines
            files.append(je_file)
            files.append(je_lines_file)

            if include_audit_events:
                events_file, written_events = self._write_audit_events(
                    out_dir,
                    self._audit_repo_factory(uow.session),
                    company_id,
                    from_date,
                    to_date,
                )
                event_count = written_events
                files.append(events_file)

        exported_at = datetime.now(timezone.utc)

        manifest_file = self._write_manifest(
            out_dir,
            company_id=company_id,
            from_date=from_date,
            to_date=to_date,
            include_audit_events=include_audit_events,
            exported_at=exported_at,
            files=files,
            posted_journal_entry_count=je_count,
            posted_journal_line_count=line_count,
            audit_event_count=event_count,
        )
        files.append(manifest_file)

        return AuditExportResultDTO(
            company_id=company_id,
            from_date=from_date,
            to_date=to_date,
            output_directory=str(out_dir),
            exported_at=exported_at,
            files=tuple(files),
            posted_journal_entry_count=je_count,
            posted_journal_line_count=line_count,
            audit_event_count=event_count,
        )

    # ------------------------------------------------------------------ #
    # Internals                                                           #
    # ------------------------------------------------------------------ #

    def _write_journal_entries(
        self, out_dir: Path, entries: list
    ) -> tuple[AuditExportFileDTO, AuditExportFileDTO, int]:
        je_path = out_dir / "journal_entries.csv"
        je_lines_path = out_dir / "journal_entry_lines.csv"
        written_lines = 0

        with je_path.open("w", encoding="utf-8", newline="") as je_handle, \
                je_lines_path.open("w", encoding="utf-8", newline="") as line_handle:
            je_writer = csv.writer(je_handle)
            je_writer.writerow([
                "journal_entry_id",
                "entry_number",
                "entry_date",
                "transaction_date",
                "journal_type_code",
                "status_code",
                "reference_text",
                "description",
                "source_module_code",
                "source_document_type",
                "source_document_id",
                "posted_at",
                "total_debit",
                "total_credit",
            ])
            line_writer = csv.writer(line_handle)
            line_writer.writerow([
                "journal_entry_id",
                "entry_number",
                "line_number",
                "account_id",
                "account_code",
                "account_name",
                "line_description",
                "debit_amount",
                "credit_amount",
            ])
            for entry in entries:
                total_debit = sum((line.debit_amount for line in entry.lines), Decimal("0"))
                total_credit = sum((line.credit_amount for line in entry.lines), Decimal("0"))
                je_writer.writerow([
                    entry.id,
                    entry.entry_number or "",
                    _fmt_date(entry.entry_date),
                    _fmt_date(entry.transaction_date),
                    entry.journal_type_code,
                    entry.status_code,
                    entry.reference_text or "",
                    entry.description or "",
                    entry.source_module_code or "",
                    entry.source_document_type or "",
                    entry.source_document_id if entry.source_document_id is not None else "",
                    _fmt_datetime(entry.posted_at),
                    f"{total_debit:.2f}",
                    f"{total_credit:.2f}",
                ])
                for line in sorted(entry.lines, key=lambda ln: ln.line_number):
                    account = line.account
                    line_writer.writerow([
                        entry.id,
                        entry.entry_number or "",
                        line.line_number,
                        line.account_id,
                        account.account_code if account is not None else "",
                        account.account_name if account is not None else "",
                        line.line_description or "",
                        f"{line.debit_amount:.2f}",
                        f"{line.credit_amount:.2f}",
                    ])
                    written_lines += 1

        return (
            _file_dto(je_path, len(entries)),
            _file_dto(je_lines_path, written_lines),
            written_lines,
        )

    def _write_audit_events(
        self,
        out_dir: Path,
        repo: AuditEventRepository,
        company_id: int,
        from_date: date,
        to_date: date,
    ) -> tuple[AuditExportFileDTO, int]:
        path = out_dir / "audit_events.csv"
        written = 0
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow([
                "audit_event_id",
                "created_at",
                "module_code",
                "event_type_code",
                "entity_type",
                "entity_id",
                "actor_user_id",
                "actor_display_name",
                "description",
                "detail_json",
            ])
            offset = 0
            from_dt = _start_of_day(from_date)
            to_dt = _end_of_day(to_date)
            while True:
                batch = repo.list_by_company(
                    company_id,
                    from_date=from_dt,
                    to_date=to_dt,
                    limit=_AUDIT_PAGE_SIZE,
                    offset=offset,
                )
                if not batch:
                    break
                for event in batch:
                    writer.writerow([
                        event.id,
                        _fmt_datetime(event.created_at),
                        event.module_code,
                        event.event_type_code,
                        event.entity_type,
                        event.entity_id if event.entity_id is not None else "",
                        event.actor_user_id if event.actor_user_id is not None else "",
                        event.actor_display_name or "",
                        event.description,
                        event.detail_json or "",
                    ])
                    written += 1
                if len(batch) < _AUDIT_PAGE_SIZE:
                    break
                offset += _AUDIT_PAGE_SIZE
        return _file_dto(path, written), written

    def _write_manifest(
        self,
        out_dir: Path,
        *,
        company_id: int,
        from_date: date,
        to_date: date,
        include_audit_events: bool,
        exported_at: datetime,
        files: list[AuditExportFileDTO],
        posted_journal_entry_count: int,
        posted_journal_line_count: int,
        audit_event_count: int,
    ) -> AuditExportFileDTO:
        manifest_path = out_dir / "manifest.json"
        manifest = {
            "company_id": company_id,
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "include_audit_events": include_audit_events,
            "exported_at_utc": exported_at.isoformat(),
            "counts": {
                "posted_journal_entries": posted_journal_entry_count,
                "posted_journal_lines": posted_journal_line_count,
                "audit_events": audit_event_count,
            },
            "files": [
                {
                    "name": f.relative_name,
                    "row_count": f.row_count,
                    "byte_size": f.byte_size,
                    "sha256": _sha256(Path(f.absolute_path)),
                }
                for f in files
            ],
        }
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return _file_dto(manifest_path, len(files))

    @staticmethod
    def _validate_date_range(from_date: date, to_date: date) -> None:
        if from_date is None or to_date is None:
            raise ValidationError("Both from-date and to-date are required.")
        if to_date < from_date:
            raise ValidationError("To-date must be on or after from-date.")


# ---------------------------------------------------------------------- #
# Helpers                                                                 #
# ---------------------------------------------------------------------- #


def _file_dto(path: Path, row_count: int) -> AuditExportFileDTO:
    return AuditExportFileDTO(
        relative_name=path.name,
        absolute_path=str(path),
        row_count=row_count,
        byte_size=path.stat().st_size if path.exists() else 0,
    )


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _start_of_day(d: date) -> datetime:
    return datetime.combine(d, time.min)


def _end_of_day(d: date) -> datetime:
    return datetime.combine(d, time.max)


def _fmt_date(value: date | None) -> str:
    if value is None:
        return ""
    return value.isoformat()


def _fmt_datetime(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.isoformat()
