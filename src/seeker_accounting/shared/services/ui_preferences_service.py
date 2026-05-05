"""Lightweight local UI preference store.

The store is intentionally outside the business database: density and other
comfort settings are per-user workstation preferences, not accounting facts.
"""
from __future__ import annotations

import json
import logging
import platform
from pathlib import Path

logger = logging.getLogger(__name__)

_FILENAME = "ui_prefs.json"
_DEFAULT_DENSITY = "comfortable"
_VALID_DENSITIES = {"comfortable", "dense"}
_TELEMETRY_OPT_IN_KEY = "telemetry_opted_in"
_DEFAULT_SERVICE: UiPreferencesService | None = None


def _prefs_path() -> Path:
    if platform.system() == "Windows":
        base = Path.home() / "AppData" / "Local" / "SeekerAccounting"
    else:
        base = Path.home() / ".config" / "SeekerAccounting"
    base.mkdir(parents=True, exist_ok=True)
    return base / _FILENAME


class UiPreferencesService:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _prefs_path()
        self._data: dict = self._load()

    def get_table_density(self) -> str:
        value = str(self._data.get("table_density", _DEFAULT_DENSITY))
        return value if value in _VALID_DENSITIES else _DEFAULT_DENSITY

    def set_table_density(self, density: str) -> None:
        if density not in _VALID_DENSITIES:
            raise ValueError("table density must be 'comfortable' or 'dense'")
        if self._data.get("table_density") == density:
            return
        self._data["table_density"] = density
        self._save()

    def get_telemetry_opted_in(self) -> bool:
        return self.get_flag(_TELEMETRY_OPT_IN_KEY, False)

    def set_telemetry_opted_in(self, value: bool) -> None:
        self.set_flag(_TELEMETRY_OPT_IN_KEY, value)

    def get_flag(self, key: str, default: bool = False) -> bool:
        return bool(self._data.get(key, default))

    def set_flag(self, key: str, value: bool) -> None:
        if self._data.get(key) == bool(value):
            return
        self._data[key] = bool(value)
        self._save()

    def _load(self) -> dict:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("ui_prefs: could not load %s; starting fresh", self._path)
            return {}

    def _save(self) -> None:
        try:
            self._path.write_text(json.dumps(self._data, indent=2, sort_keys=True), encoding="utf-8")
        except Exception:
            logger.warning("ui_prefs: could not save %s", self._path)


def get_default_ui_preferences_service() -> UiPreferencesService:
    global _DEFAULT_SERVICE
    if _DEFAULT_SERVICE is None:
        _DEFAULT_SERVICE = UiPreferencesService()
    return _DEFAULT_SERVICE