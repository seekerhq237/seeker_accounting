from __future__ import annotations

import io
import sqlite3
import zipfile
from pathlib import Path

import pytest

from seeker_accounting.config.paths import build_runtime_paths, ensure_runtime_directories
from seeker_accounting.config.settings import AppSettings
from seeker_accounting.modules.administration.services.backup_export_service import BackupExportService
from seeker_accounting.modules.administration.services.backup_merge_service import BackupMergeService
from seeker_accounting.platform.exceptions import ValidationError


def _settings(tmp_path: Path, database_url: str) -> AppSettings:
    runtime_paths = build_runtime_paths(tmp_path / "runtime")
    ensure_runtime_directories(runtime_paths)
    return AppSettings(
        app_name="Seeker",
        organization_name="Test",
        window_title="Seeker",
        environment="test",
        theme_name="light",
        current_user_display_name="Tester",
        runtime_paths=runtime_paths,
        database_url=database_url,
        log_level="INFO",
    )


def test_backup_export_snapshots_active_database_url_with_wal_state(tmp_path: Path) -> None:
    active_db = tmp_path / "active.db"
    with sqlite3.connect(active_db) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE ordinary_rows (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
        conn.execute("CREATE TABLE system_admin_credentials (id INTEGER PRIMARY KEY, secret TEXT NOT NULL)")
        conn.execute("INSERT INTO ordinary_rows (name) VALUES ('committed through WAL')")
        conn.execute("INSERT INTO system_admin_credentials (secret) VALUES ('local only')")
        conn.commit()

        service = BackupExportService(
            _settings(tmp_path, f"sqlite:///{active_db.as_posix()}")
        )
        inner_zip_bytes = service._build_inner_zip()

    with zipfile.ZipFile(io.BytesIO(inner_zip_bytes), "r") as inner:
        exported_db = inner.read("database.db")

    exported_path = tmp_path / "exported.db"
    exported_path.write_bytes(exported_db)
    with sqlite3.connect(exported_path) as conn:
        rows = conn.execute("SELECT name FROM ordinary_rows").fetchall()
        stripped = conn.execute("SELECT secret FROM system_admin_credentials").fetchall()

    assert rows == [("committed through WAL",)]
    assert stripped == []


def test_backup_merge_rejects_unsafe_asset_paths(tmp_path: Path) -> None:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED) as inner:
        inner.writestr("assets/user_avatars/../escape.txt", b"nope")

    with pytest.raises(ValidationError, match="unsafe asset path"):
        BackupMergeService._extract_assets(payload.getvalue(), tmp_path)

    assert not (tmp_path / "escape.txt").exists()
