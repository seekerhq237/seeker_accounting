from __future__ import annotations

import ast
import logging
import sqlite3
import sys
from pathlib import Path

import seeker_accounting.db.migrations as migrations_package
from seeker_accounting.config.paths import PROJECT_ROOT

logger = logging.getLogger(__name__)

_FROZEN = getattr(sys, "frozen", False)

if _FROZEN:
    _BUNDLE_DIR = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    ALEMBIC_INI_PATH: Path | None = _BUNDLE_DIR / "alembic.ini"
    MIGRATIONS_PATH = _BUNDLE_DIR / "seeker_accounting" / "db" / "migrations"
else:
    _SOURCE_ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"
    ALEMBIC_INI_PATH = _SOURCE_ALEMBIC_INI if _SOURCE_ALEMBIC_INI.exists() else None
    MIGRATIONS_PATH = Path(migrations_package.__file__).resolve().parent


def build_alembic_config(database_url: str) -> "Config":
    from alembic.config import Config

    config = Config(str(ALEMBIC_INI_PATH)) if ALEMBIC_INI_PATH is not None else Config()
    config.set_main_option("script_location", str(MIGRATIONS_PATH))
    config.set_main_option("sqlalchemy.url", database_url)
    config.attributes["seeker_database_url"] = database_url
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

        script_heads = _migration_script_heads()
        if script_heads != {expected_head}:
            return False

        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.execute("SELECT version_num FROM alembic_version")
            current_revisions = {row[0] for row in cursor.fetchall() if row[0]}
        finally:
            conn.close()

        return current_revisions == {expected_head}
    except Exception:
        return False


def _migration_script_heads() -> set[str]:
    """Return migration heads by reading revision metadata without importing Alembic."""
    versions_path = MIGRATIONS_PATH / "versions"
    if not versions_path.exists():
        return set()

    revisions: set[str] = set()
    down_revisions: set[str] = set()
    for path in versions_path.glob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception:
            return set()

        revision: str | None = None
        down_revision: object = None
        for node in tree.body:
            target_names: set[str]
            value_node: ast.AST | None
            if isinstance(node, ast.Assign):
                target_names = {
                    target.id for target in node.targets if isinstance(target, ast.Name)
                }
                value_node = node.value
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                target_names = {node.target.id}
                value_node = node.value
            else:
                continue
            if value_node is None:
                continue

            if "revision" in target_names:
                value = ast.literal_eval(value_node)
                if isinstance(value, str):
                    revision = value
            elif "down_revision" in target_names:
                down_revision = ast.literal_eval(value_node)

        if revision:
            revisions.add(revision)
        if isinstance(down_revision, str):
            down_revisions.add(down_revision)
        elif isinstance(down_revision, (tuple, list, set)):
            down_revisions.update(value for value in down_revision if isinstance(value, str))

    return revisions - down_revisions


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
