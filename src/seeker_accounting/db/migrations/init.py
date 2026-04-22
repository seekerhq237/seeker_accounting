from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path

from seeker_accounting.config.paths import PROJECT_ROOT

logger = logging.getLogger(__name__)

_FROZEN = getattr(sys, "frozen", False)

if _FROZEN:
    _BUNDLE_DIR = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    ALEMBIC_INI_PATH = _BUNDLE_DIR / "alembic.ini"
    MIGRATIONS_PATH = _BUNDLE_DIR / "seeker_accounting" / "db" / "migrations"
else:
    ALEMBIC_INI_PATH = PROJECT_ROOT / "alembic.ini"
    MIGRATIONS_PATH = PROJECT_ROOT / "src" / "seeker_accounting" / "db" / "migrations"


def build_alembic_config(database_url: str) -> "Config":
    from alembic.config import Config

    config = Config(str(ALEMBIC_INI_PATH))
    config.set_main_option("script_location", str(MIGRATIONS_PATH))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _sentinel_path_for(database_url: str) -> Path | None:
    """Return the path to the .migration_head sentinel file for a SQLite database."""
    if not database_url.startswith("sqlite:///"):
        return None
    db_path = database_url.replace("sqlite:///", "")
    return Path(db_path).with_suffix(".migration_head")


def _try_fast_sentinel_check(database_url: str) -> bool:
    """Check if DB is at head using only sqlite3 + a sentinel file. No Alembic import needed."""
    sentinel = _sentinel_path_for(database_url)
    if sentinel is None:
        return False

    db_path = database_url.replace("sqlite:///", "")
    if not Path(db_path).exists() or not sentinel.exists():
        return False

    try:
        expected_head = sentinel.read_text(encoding="utf-8").strip()
        if not expected_head:
            return False

        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.execute("SELECT version_num FROM alembic_version LIMIT 1")
            row = cursor.fetchone()
        finally:
            conn.close()

        if row is None:
            return False

        return row[0] == expected_head
    except Exception:
        return False


def _write_sentinel(database_url: str, head_rev: str) -> None:
    """Write the current head revision to a sentinel file for fast subsequent checks."""
    sentinel = _sentinel_path_for(database_url)
    if sentinel is not None and head_rev:
        try:
            sentinel.write_text(head_rev, encoding="utf-8")
        except Exception:
            logger.debug("Could not write migration sentinel file.", exc_info=True)


def _is_at_head(database_url: str) -> tuple[bool, str | None]:
    """Return (at_head, head_revision) using full Alembic introspection."""
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory
    from sqlalchemy import create_engine

    try:
        config = build_alembic_config(database_url)
        script = ScriptDirectory.from_config(config)
        head_rev = script.get_current_head()
        if head_rev is None:
            return False, None

        engine = create_engine(database_url)
        with engine.connect() as conn:
            context = MigrationContext.configure(conn)
            current_rev = context.get_current_revision()
        engine.dispose()
        return current_rev == head_rev, head_rev
    except Exception:
        return False, None


def ensure_database_schema(database_url: str) -> None:
    # Fast path: sentinel file + sqlite3 — no Alembic import needed
    if _try_fast_sentinel_check(database_url):
        logger.debug("Database schema at head (sentinel fast-path) — skipping migration.")
        return

    # Slow path: full Alembic check
    at_head, head_rev = _is_at_head(database_url)
    if at_head and head_rev:
        _write_sentinel(database_url, head_rev)
        logger.debug("Database schema already at head — skipping migration.")
        return

    from alembic import command

    command.upgrade(build_alembic_config(database_url), "head")

    # Write sentinel after successful migration
    _, new_head = _is_at_head(database_url)
    if new_head:
        _write_sentinel(database_url, new_head)


__all__ = ["build_alembic_config", "ensure_database_schema"]
