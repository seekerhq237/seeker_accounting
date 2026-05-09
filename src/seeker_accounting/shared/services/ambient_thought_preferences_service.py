"""Per-user preference store for the Ambient Intelligence overlay.

Storage matches the convention established by
`SidebarPreferencesService` — a JSON file in the local app-data folder.
The service is intentionally tiny: it owns no UI, no providers, and no
business logic. It exists so the overlay, the profile menu, and the
command palette can all read and write the same persisted state.

Schema (on disk):
```
{
  "enabled": true,
  "snoozed_until": "2026-05-09T18:00:00",
  "muted_codes": ["payroll.deadline.approaching"],
  "mode": "minimal",
  "position": {"anchor": "bottom_right", "x_ratio": 0.96, "y_ratio": 0.94}
}
```

The class is a `QObject` so it can broadcast `preferences_changed` —
multiple shell consumers (overlay, profile menu, command palette) hold
the SAME instance via the service registry, so a write from any of them
updates the others live without requiring a polling loop.
"""
from __future__ import annotations

import json
import logging
import platform
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from PySide6.QtCore import QObject, Signal


logger = logging.getLogger(__name__)


_FILENAME = "ambient_thought_prefs.json"

AmbientMode = Literal["minimal", "standard"]
AmbientAnchor = Literal["top_left", "top_right", "bottom_left", "bottom_right"]


def _prefs_path() -> Path:
    if platform.system() == "Windows":
        base = Path.home() / "AppData" / "Local" / "SeekerAccounting"
    else:
        base = Path.home() / ".config" / "SeekerAccounting"
    base.mkdir(parents=True, exist_ok=True)
    return base / _FILENAME


@dataclass(frozen=True, slots=True)
class AmbientPosition:
    anchor: AmbientAnchor = "bottom_right"
    x_ratio: float = 0.96
    y_ratio: float = 0.94


class AmbientThoughtPreferencesService(QObject):
    """Persisted, broadcasting preferences for ambient thoughts.

    Holding a single shared instance is the contract; do not construct
    this elsewhere if a registry-provided one exists.
    """

    preferences_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._path = _prefs_path()
        self._data: dict = self._load()

    # ── Master switch ────────────────────────────────────────────────

    def is_enabled(self) -> bool:
        return bool(self._data.get("enabled", True))

    def set_enabled(self, value: bool) -> None:
        if bool(self._data.get("enabled", True)) == bool(value):
            return
        self._data["enabled"] = bool(value)
        # Turning back on cancels any active snooze, otherwise the user
        # would toggle "On" and still see nothing for an hour.
        if value:
            self._data["snoozed_until"] = None
        self._save_and_emit()

    def toggle_enabled(self) -> bool:
        new_value = not self.is_enabled()
        self.set_enabled(new_value)
        return new_value

    # ── Snooze ───────────────────────────────────────────────────────

    def snoozed_until(self) -> datetime | None:
        raw = self._data.get("snoozed_until")
        if not raw:
            return None
        try:
            return datetime.fromisoformat(str(raw))
        except (TypeError, ValueError):
            return None

    def is_snoozed(self, *, now: datetime | None = None) -> bool:
        until = self.snoozed_until()
        if until is None:
            return False
        return (now or datetime.now()) < until

    def snooze_for(self, minutes: int) -> None:
        if minutes <= 0:
            return
        until = datetime.now() + timedelta(minutes=minutes)
        self._data["snoozed_until"] = until.isoformat()
        self._save_and_emit()

    def clear_snooze(self) -> None:
        if not self._data.get("snoozed_until"):
            return
        self._data["snoozed_until"] = None
        self._save_and_emit()

    # ── Mute by code ─────────────────────────────────────────────────

    def muted_codes(self) -> tuple[str, ...]:
        raw = self._data.get("muted_codes") or []
        if not isinstance(raw, list):
            return ()
        return tuple(str(c) for c in raw)

    def is_muted(self, thought_code: str) -> bool:
        return thought_code in self.muted_codes()

    def mute(self, thought_code: str) -> None:
        muted = list(self.muted_codes())
        if thought_code in muted:
            return
        muted.append(thought_code)
        self._data["muted_codes"] = muted
        self._save_and_emit()

    def unmute(self, thought_code: str) -> None:
        muted = [c for c in self.muted_codes() if c != thought_code]
        if len(muted) == len(self.muted_codes()):
            return
        self._data["muted_codes"] = muted
        self._save_and_emit()

    # ── Mode ─────────────────────────────────────────────────────────

    def mode(self) -> AmbientMode:
        raw = str(self._data.get("mode", "minimal"))
        return "standard" if raw == "standard" else "minimal"

    def set_mode(self, value: AmbientMode) -> None:
        if self.mode() == value:
            return
        self._data["mode"] = value
        self._save_and_emit()

    # ── Position ─────────────────────────────────────────────────────

    def position(self) -> AmbientPosition:
        raw = self._data.get("position") or {}
        if not isinstance(raw, dict):
            return AmbientPosition()
        anchor = str(raw.get("anchor", "bottom_right"))
        if anchor not in ("top_left", "top_right", "bottom_left", "bottom_right"):
            anchor = "bottom_right"
        try:
            x_ratio = float(raw.get("x_ratio", 0.96))
            y_ratio = float(raw.get("y_ratio", 0.94))
        except (TypeError, ValueError):
            x_ratio, y_ratio = 0.96, 0.94
        # Clamp to keep a corrupt preference file from sending the chip off-screen.
        x_ratio = min(max(x_ratio, 0.0), 1.0)
        y_ratio = min(max(y_ratio, 0.0), 1.0)
        return AmbientPosition(anchor=anchor, x_ratio=x_ratio, y_ratio=y_ratio)  # type: ignore[arg-type]

    def set_position(self, position: AmbientPosition) -> None:
        self._data["position"] = {
            "anchor": position.anchor,
            "x_ratio": float(position.x_ratio),
            "y_ratio": float(position.y_ratio),
        }
        # Position writes happen on every drag-release; persist but do not
        # spam preferences_changed — the overlay already knows where it is.
        self._save(emit=False)

    # ── Persistence helpers ──────────────────────────────────────────

    def _load(self) -> dict:
        try:
            if not self._path.exists():
                return {}
            with self._path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
            return {}
        except Exception:
            logger.warning(
                "Failed to load ambient thought preferences from %s; using defaults.",
                self._path,
                exc_info=True,
            )
            return {}

    def _save(self, *, emit: bool = True) -> None:
        try:
            with self._path.open("w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except Exception:
            logger.warning(
                "Failed to write ambient thought preferences to %s.",
                self._path,
                exc_info=True,
            )
        if emit:
            self.preferences_changed.emit()

    def _save_and_emit(self) -> None:
        self._save(emit=True)
