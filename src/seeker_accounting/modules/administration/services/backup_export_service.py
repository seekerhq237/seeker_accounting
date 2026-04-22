"""BackupExportService — creates encrypted .seekerbackup archive files.

Archive format:
    backup.seekerbackup          (renamed ZIP)
    ├── manifest.json            unencrypted: app_version, export_date, salt (hex), nonce (hex)
    └── data.enc                 AES-256-GCM(key, inner_zip_bytes)
        [inner ZIP contains]
        ├── database.db
        └── assets/
            ├── user_avatars/<files>
            └── company_logos/<files>

Key derivation: PBKDF2HMAC / SHA-256 / 600 000 iterations / 16-byte random salt → 32-byte key.
Encryption:     AES-256-GCM with 12-byte random nonce; 16-byte auth tag appended to ciphertext.

system_admin_credentials is stripped from the exported database — it is a
machine-local secret and must never travel.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError as SAOperationalError

from seeker_accounting.config.settings import AppSettings

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

_PBKDF2_ITERATIONS = 600_000
_STRIP_TABLES = frozenset([
    "system_admin_credentials",
    "authentication_lockouts",
    "password_history",
    "user_sessions",
])

APP_VERSION = "1.0"


def _derive_key(password: str, salt: bytes) -> bytes:
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=_PBKDF2_ITERATIONS,
    )
    return kdf.derive(password.encode("utf-8"))


def _encrypt(key: bytes, nonce: bytes, plaintext: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    aesgcm = AESGCM(key)
    return aesgcm.encrypt(nonce, plaintext, None)


def _decrypt(key: bytes, nonce: bytes, ciphertext: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)


class BackupExportService:
    """Produces an encrypted .seekerbackup file from the live application data."""

    def __init__(self, settings: AppSettings, audit_service: "AuditService | None" = None) -> None:
        self._settings = settings
        self._audit_service = audit_service

    # ── Public API ────────────────────────────────────────────────────────────

    def export(self, password: str, output_path: Path) -> None:
        """Export the full system to *output_path*.

        The file is written atomically: a temp file is finalised before renaming
        to the target path.

        Raises:
            ValueError: if *password* is empty.
            RuntimeError: on unexpected I/O failure.
        """
        if not password:
            raise ValueError("Export password must not be empty.")

        salt = os.urandom(16)
        nonce = os.urandom(12)
        key = _derive_key(password, salt)

        inner_zip_bytes = self._build_inner_zip()
        encrypted = _encrypt(key, nonce, inner_zip_bytes)

        manifest = {
            "app_version": APP_VERSION,
            "export_date": datetime.now(timezone.utc).isoformat(),
            "salt_hex": salt.hex(),
            "nonce_hex": nonce.hex(),
        }

        tmp_path = output_path.with_suffix(".tmp")
        try:
            with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as outer:
                outer.writestr("manifest.json", json.dumps(manifest, indent=2))
                outer.writestr("data.enc", encrypted)
            tmp_path.replace(output_path)
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise

        self._record_audit(str(output_path))

    # ── Internals ─────────────────────────────────────────────────────────────

    def _build_inner_zip(self) -> bytes:
        """Return in-memory ZIP bytes containing the sanitised DB + assets."""
        data_dir = self._settings.runtime_paths.data
        db_file = self._settings.runtime_paths.database_file

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as inner:
            # ── Database (sanitised copy) ──────────────────────────────────
            sanitised_db = self._sanitised_db_bytes(db_file)
            inner.writestr("database.db", sanitised_db)

            # ── Asset files ───────────────────────────────────────────────
            for asset_subdir in ("user_avatars", "company_logos"):
                asset_dir = data_dir / asset_subdir
                if not asset_dir.exists():
                    continue
                for asset_file in sorted(asset_dir.iterdir()):
                    if asset_file.is_file():
                        arcname = f"assets/{asset_subdir}/{asset_file.name}"
                        inner.write(asset_file, arcname)

        return buf.getvalue()

    @staticmethod
    def _sanitised_db_bytes(db_file: Path) -> bytes:
        """Return bytes of a copy of the DB with sensitive tables emptied."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            sanitised_path = Path(tmp_dir) / "export.db"
            shutil.copy2(db_file, sanitised_path)

            engine = create_engine(f"sqlite:///{sanitised_path.as_posix()}")
            try:
                with engine.begin() as conn:
                    for table in _STRIP_TABLES:
                        try:
                            conn.execute(text(f"DELETE FROM {table}"))  # noqa: S608
                        except SAOperationalError:
                            pass  # table may not exist in older schemas
            finally:
                engine.dispose()

            return sanitised_path.read_bytes()

    def _record_audit(self, output_path: str) -> None:
        if self._audit_service is None:
            return
        from seeker_accounting.modules.audit.dto.audit_event_dto import RecordAuditEventCommand
        from seeker_accounting.modules.audit.event_type_catalog import (
            DATABASE_BACKUP_CREATED,
            MODULE_AUTH,
        )
        try:
            self._audit_service.record_event(
                0,
                RecordAuditEventCommand(
                    event_type_code=DATABASE_BACKUP_CREATED,
                    module_code=MODULE_AUTH,
                    entity_type="DatabaseBackup",
                    entity_id=None,
                    description=f"Database backup created: {output_path}",
                ),
            )
        except Exception:
            pass  # Audit must not break business operations
