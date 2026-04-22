"""BackupAnalysisService — decrypts a .seekerbackup archive and analyses its
contents for conflict detection before any merge is applied.

Returns a BackupAnalysisDTO describing:
- companies found in the backup and whether each conflicts with an existing target record
- users found in the backup and whether each conflicts with an existing target record
- approximate per-table row counts (informational)
"""
from __future__ import annotations

import io
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Callable

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import OperationalError as SAOperationalError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.dto.backup_dto import (
    BackupAnalysisDTO,
    BackupManifest,
    CompanyImportItem,
    UserImportItem,
)
from seeker_accounting.modules.administration.services.backup_export_service import (
    _derive_key,
    _decrypt,
)
from seeker_accounting.platform.exceptions import ValidationError

_SUMMARY_TABLES = (
    "companies",
    "users",
    "accounts",
    "fiscal_years",
    "fiscal_periods",
    "journal_entries",
    "journal_entry_lines",
    "customers",
    "suppliers",
    "sales_invoices",
    "purchase_bills",
    "financial_accounts",
    "treasury_transactions",
    "items",
    "inventory_documents",
    "assets",
    "employees",
    "payroll_runs",
)

_CONFLICT_SUFFIX = " (Imported)"


class BackupAnalysisService:
    """Read-only analysis of a .seekerbackup archive before merge."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        session_factory: Callable[[Session], Session] | None = None,
    ) -> None:
        self._uow_factory = unit_of_work_factory

    # ── Public API ────────────────────────────────────────────────────────────

    def analyse(self, backup_path: Path, password: str) -> BackupAnalysisDTO:
        """Decrypt *backup_path* and return conflict analysis.

        Raises:
            ValidationError: on wrong password, corrupt archive, or unsupported format.
        """
        if not password:
            raise ValidationError("Backup password must not be empty.")

        manifest, inner_zip_bytes = self._open_and_decrypt(backup_path, password)

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_db = Path(tmp_dir) / "backup.db"
            self._extract_db(inner_zip_bytes, tmp_db)
            companies, users, summary = self._analyse_db(manifest, tmp_db)

        return BackupAnalysisDTO(
            manifest=manifest,
            companies=tuple(companies),
            users=tuple(users),
            record_summary=summary,
        )

    # ── Internals ─────────────────────────────────────────────────────────────

    @staticmethod
    def _open_and_decrypt(backup_path: Path, password: str) -> tuple[BackupManifest, bytes]:
        """Open outer ZIP and decrypt data.enc → inner ZIP bytes."""
        try:
            with zipfile.ZipFile(backup_path, "r") as outer:
                names = outer.namelist()
                if "manifest.json" not in names or "data.enc" not in names:
                    raise ValidationError(
                        "This file does not appear to be a valid Seeker backup."
                    )
                manifest_raw = outer.read("manifest.json")
                enc_bytes = outer.read("data.enc")
        except zipfile.BadZipFile as exc:
            raise ValidationError(
                "The backup file is corrupt or not a valid Seeker backup."
            ) from exc

        try:
            manifest_dict = json.loads(manifest_raw)
            salt = bytes.fromhex(manifest_dict["salt_hex"])
            nonce = bytes.fromhex(manifest_dict["nonce_hex"])
            manifest = BackupManifest(
                app_version=manifest_dict.get("app_version", ""),
                export_date=manifest_dict.get("export_date", ""),
                salt_hex=manifest_dict["salt_hex"],
                nonce_hex=manifest_dict["nonce_hex"],
            )
        except (KeyError, ValueError) as exc:
            raise ValidationError(
                "The backup manifest is missing required fields."
            ) from exc

        try:
            key = _derive_key(password, salt)
            inner_zip_bytes = _decrypt(key, nonce, enc_bytes)
        except Exception as exc:
            raise ValidationError(
                "Incorrect password or the backup file is corrupt."
            ) from exc

        return manifest, inner_zip_bytes

    @staticmethod
    def _extract_db(inner_zip_bytes: bytes, dest_db: Path) -> None:
        """Extract database.db from the inner ZIP to *dest_db*."""
        try:
            with zipfile.ZipFile(io.BytesIO(inner_zip_bytes), "r") as inner:
                if "database.db" not in inner.namelist():
                    raise ValidationError("Backup archive does not contain a database file.")
                dest_db.write_bytes(inner.read("database.db"))
        except zipfile.BadZipFile as exc:
            raise ValidationError("Backup data is corrupt.") from exc

    def _analyse_db(
        self,
        manifest: BackupManifest,
        db_path: Path,
    ) -> tuple[list[CompanyImportItem], list[UserImportItem], dict[str, int]]:
        """Query the backup DB and compare against the live target DB."""
        engine = create_engine(f"sqlite:///{db_path.as_posix()}")
        try:
            with engine.connect() as src_conn:
                return self._compare(src_conn)
        finally:
            engine.dispose()

    def _compare(
        self, src: Connection
    ) -> tuple[list[CompanyImportItem], list[UserImportItem], dict[str, int]]:
        with self._uow_factory() as uow:
            tgt = uow.session.connection()

            # ── Existing target names ──────────────────────────────────────
            existing_legal_names: set[str] = {
                row[0].lower()
                for row in tgt.execute(
                    text("SELECT legal_name FROM companies")
                ).fetchall()
            }
            existing_usernames: set[str] = {
                row[0].lower()
                for row in tgt.execute(
                    text("SELECT username FROM users")
                ).fetchall()
            }

            # ── Companies ─────────────────────────────────────────────────
            company_items: list[CompanyImportItem] = []
            for row in src.execute(text("SELECT id, legal_name, display_name FROM companies")):
                m = row._mapping
                conflict = m["legal_name"].lower() in existing_legal_names
                resolved = m["legal_name"] + _CONFLICT_SUFFIX if conflict else m["legal_name"]
                company_items.append(
                    CompanyImportItem(
                        src_id=m["id"],
                        legal_name=m["legal_name"],
                        display_name=m["display_name"],
                        conflict=conflict,
                        resolved_name=resolved,
                    )
                )

            # ── Users ─────────────────────────────────────────────────────
            user_items: list[UserImportItem] = []
            for row in src.execute(text("SELECT id, username, display_name FROM users")):
                m = row._mapping
                conflict = m["username"].lower() in existing_usernames
                user_items.append(
                    UserImportItem(
                        src_id=m["id"],
                        username=m["username"],
                        display_name=m["display_name"],
                        conflict=conflict,
                        resolved_username=m["username"],
                    )
                )

            # ── Row counts (informational) ─────────────────────────────────
            summary: dict[str, int] = {}
            for tbl in _SUMMARY_TABLES:
                try:
                    count = src.execute(text(f"SELECT COUNT(*) FROM {tbl}")).fetchone()[0]  # noqa: S608
                    summary[tbl] = count
                except SAOperationalError:
                    pass  # table may not exist in older backup schemas

        return company_items, user_items, summary
