"""
License ledger — JSON-backed record of all issued licenses.

Stores issued licenses with metadata (customer, email, notes, status)
in a local JSON file for tracking and management.
"""
from __future__ import annotations

import datetime
import json
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal


LicenseStatus = Literal["active", "revoked"]

_LEDGER_FILENAME = "license_ledger.json"


@dataclass(slots=True)
class LicenseRecord:
    """A single issued license entry in the ledger."""
    id: int
    key: str
    customer: str
    email: str
    edition: int
    issued_at: str          # ISO date
    expires_at: str         # ISO date
    status: LicenseStatus
    notes: str = ""
    revoked_at: str = ""    # ISO date, empty if not revoked


@dataclass(slots=True)
class Ledger:
    """In-memory representation of the license ledger."""
    next_id: int = 1
    records: list[LicenseRecord] = field(default_factory=list)


class LedgerStore:
    """Reads and writes the license ledger JSON file."""

    def __init__(self, keys_dir: Path) -> None:
        self._path = keys_dir / _LEDGER_FILENAME
        self._ledger = self._load()

    @property
    def path(self) -> Path:
        return self._path

    # ── Queries ───────────────────────────────────────────────────────

    def all_records(self) -> list[LicenseRecord]:
        return list(self._ledger.records)

    def active_records(self) -> list[LicenseRecord]:
        return [r for r in self._ledger.records if r.status == "active"]

    def get_by_id(self, record_id: int) -> LicenseRecord | None:
        for r in self._ledger.records:
            if r.id == record_id:
                return r
        return None

    def search(self, query: str) -> list[LicenseRecord]:
        q = query.lower()
        return [
            r for r in self._ledger.records
            if q in r.customer.lower()
            or q in r.email.lower()
            or q in r.notes.lower()
            or q in str(r.id)
        ]

    # ── Mutations ─────────────────────────────────────────────────────

    def add(
        self,
        key: str,
        customer: str,
        email: str,
        edition: int,
        issued_at: datetime.date,
        expires_at: datetime.date,
        notes: str = "",
    ) -> LicenseRecord:
        """Add a new license record and persist."""
        record = LicenseRecord(
            id=self._ledger.next_id,
            key=key,
            customer=customer,
            email=email,
            edition=edition,
            issued_at=issued_at.isoformat(),
            expires_at=expires_at.isoformat(),
            status="active",
            notes=notes,
        )
        self._ledger.records.append(record)
        self._ledger.next_id += 1
        self._save()
        return record

    def revoke(self, record_id: int) -> LicenseRecord:
        """Mark a license as revoked."""
        record = self.get_by_id(record_id)
        if record is None:
            raise KeyError(f"License #{record_id} not found.")
        if record.status == "revoked":
            raise ValueError(f"License #{record_id} is already revoked.")
        record.status = "revoked"
        record.revoked_at = datetime.date.today().isoformat()
        self._save()
        return record

    def update_notes(self, record_id: int, notes: str) -> LicenseRecord:
        """Update the notes field of a license record."""
        record = self.get_by_id(record_id)
        if record is None:
            raise KeyError(f"License #{record_id} not found.")
        record.notes = notes
        self._save()
        return record

    # ── Persistence ───────────────────────────────────────────────────

    def _load(self) -> Ledger:
        if not self._path.exists():
            return Ledger()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            records = [LicenseRecord(**r) for r in data.get("records", [])]
            return Ledger(
                next_id=data.get("next_id", len(records) + 1),
                records=records,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to read ledger at {self._path}: {exc}\n"
                "If the file is corrupted, restore from backup or delete it to start fresh."
            ) from exc

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)

        # Write to a temp file first, then rename for atomicity.
        tmp_path = self._path.with_suffix(".tmp")
        payload = {
            "next_id": self._ledger.next_id,
            "records": [asdict(r) for r in self._ledger.records],
        }
        tmp_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        shutil.move(str(tmp_path), str(self._path))
