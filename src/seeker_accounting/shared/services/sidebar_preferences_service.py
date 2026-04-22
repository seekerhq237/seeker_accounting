"""Lightweight per-user sidebar preference store.

Persists favorites (pinned nav_ids) and recents (last N visited nav_ids) in a
JSON file in the user's app-data directory.  No DB access, no Alembic.
"""
from __future__ import annotations

import json
import logging
import platform
from pathlib import Path

logger = logging.getLogger(__name__)

_MAX_RECENTS = 5
_FILENAME = "sidebar_prefs.json"


def _prefs_path() -> Path:
    if platform.system() == "Windows":
        base = Path.home() / "AppData" / "Local" / "SeekerAccounting"
    else:
        base = Path.home() / ".config" / "SeekerAccounting"
    base.mkdir(parents=True, exist_ok=True)
    return base / _FILENAME


class SidebarPreferencesService:
    """Read/write sidebar user preferences (favorites + recents)."""

    def __init__(self) -> None:
        self._path = _prefs_path()
        self._data: dict = self._load()

    # ── Favorites ─────────────────────────────────────────────────────────

    def get_favorites(self) -> list[str]:
        return list(self._data.get("favorites", []))

    def add_favorite(self, nav_id: str) -> None:
        favs: list[str] = self._data.setdefault("favorites", [])
        if nav_id not in favs:
            favs.append(nav_id)
            self._save()

    def remove_favorite(self, nav_id: str) -> None:
        favs: list[str] = self._data.get("favorites", [])
        if nav_id in favs:
            favs.remove(nav_id)
            self._save()

    def is_favorite(self, nav_id: str) -> bool:
        return nav_id in self._data.get("favorites", [])

    # ── Recents ───────────────────────────────────────────────────────────

    def get_recents(self) -> list[str]:
        return list(self._data.get("recents", []))

    def push_recent(self, nav_id: str) -> None:
        recents: list[str] = self._data.setdefault("recents", [])
        if nav_id in recents:
            recents.remove(nav_id)
        recents.insert(0, nav_id)
        del recents[_MAX_RECENTS:]
        self._save()

    # ── Internals ─────────────────────────────────────────────────────────

    def _load(self) -> dict:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("sidebar_prefs: could not load %s; starting fresh", self._path)
            return {}

    def _save(self) -> None:
        try:
            self._path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        except Exception:
            logger.warning("sidebar_prefs: could not save %s", self._path)
