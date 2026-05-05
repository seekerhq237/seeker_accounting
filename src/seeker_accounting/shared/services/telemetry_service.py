"""Opt-in anonymous funnel telemetry.

Telemetry is disabled by default, stores only event codes and coarse context,
and writes locally. A future sync/export layer can consume these records only
after the user has opted in.
"""
from __future__ import annotations

import json
import logging
import platform
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from seeker_accounting.shared.services.ui_preferences_service import (
    UiPreferencesService,
    get_default_ui_preferences_service,
)

logger = logging.getLogger(__name__)

_FILENAME = "telemetry_events.jsonl"
_DEFAULT_SERVICE: TelemetryService | None = None


def _telemetry_path() -> Path:
    if platform.system() == "Windows":
        base = Path.home() / "AppData" / "Local" / "SeekerAccounting"
    else:
        base = Path.home() / ".config" / "SeekerAccounting"
    base.mkdir(parents=True, exist_ok=True)
    return base / _FILENAME


@dataclass(frozen=True, slots=True)
class TelemetryEvent:
    event_code: str
    funnel: str
    step: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    context: Mapping[str, str | int | bool] = field(default_factory=dict)

    def to_record(self) -> dict[str, object]:
        return {
            "event_code": self.event_code,
            "funnel": self.funnel,
            "step": self.step,
            "occurred_at": self.occurred_at.isoformat(),
            "context": dict(self.context),
        }


class TelemetryService:
    def __init__(
        self,
        *,
        opted_in: bool | None = False,
        path: Path | None = None,
        preferences: UiPreferencesService | None = None,
    ) -> None:
        self._preferences = preferences
        self._opted_in = bool(opted_in) if opted_in is not None else None
        self._path = path or _telemetry_path()

    @property
    def opted_in(self) -> bool:
        if self._preferences is not None:
            return self._preferences.get_telemetry_opted_in()
        return bool(self._opted_in)

    def set_opted_in(self, value: bool) -> None:
        if self._preferences is not None:
            self._preferences.set_telemetry_opted_in(value)
            return
        self._opted_in = bool(value)

    def record_funnel_step(
        self,
        *,
        funnel: str,
        step: str,
        event_code: str | None = None,
        context: Mapping[str, str | int | bool] | None = None,
    ) -> bool:
        if not self.opted_in:
            return False
        event = TelemetryEvent(
            event_code=event_code or f"{funnel}.{step}",
            funnel=funnel,
            step=step,
            context=_sanitize_context(context or {}),
        )
        try:
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event.to_record(), sort_keys=True) + "\n")
            return True
        except Exception:
            logger.warning("telemetry: could not write %s", self._path, exc_info=True)
            return False


def _sanitize_context(context: Mapping[str, str | int | bool]) -> dict[str, str | int | bool]:
    clean: dict[str, str | int | bool] = {}
    for key, value in context.items():
        if key.lower() in {"name", "email", "phone", "address", "tax_identifier"}:
            continue
        if isinstance(value, str):
            clean[key] = value[:80]
        elif isinstance(value, (int, bool)):
            clean[key] = value
    return clean


def get_default_telemetry_service() -> TelemetryService:
    global _DEFAULT_SERVICE
    if _DEFAULT_SERVICE is None:
        _DEFAULT_SERVICE = TelemetryService(
            opted_in=None,
            preferences=get_default_ui_preferences_service(),
        )
    return _DEFAULT_SERVICE