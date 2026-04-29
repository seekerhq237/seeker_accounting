"""Serializable state container shared by wizard steps."""
from __future__ import annotations

import copy
import json
from typing import Any, Iterator, Mapping


class WizardState:
    """A simple, JSON-serializable key/value state bag passed between steps.

    Steps read prior step outputs by key and write their own outputs by key.
    The framework persists the state to ``wizard_runs.state_payload`` (Text/JSON)
    so a paused wizard can be resumed from a fresh process.

    Values must be JSON-serializable. Pre-validate with :meth:`assert_serializable`
    before commit.
    """

    __slots__ = ("_data",)

    def __init__(self, data: Mapping[str, Any] | None = None) -> None:
        self._data: dict[str, Any] = dict(data or {})

    # ── Mapping-style access ─────────────────────────────────────────────

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = value

    def __contains__(self, key: object) -> bool:
        return key in self._data

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def update(self, mapping: Mapping[str, Any]) -> None:
        self._data.update(mapping)

    def pop(self, key: str, default: Any = None) -> Any:
        return self._data.pop(key, default)

    # ── Snapshot / serialization ─────────────────────────────────────────

    def snapshot(self) -> dict[str, Any]:
        """Return a deep copy of the current state for safe inspection."""
        return copy.deepcopy(self._data)

    def to_json(self) -> str:
        """Serialize the state to a JSON string for persistence."""
        return json.dumps(self._data, default=str, sort_keys=True)

    @classmethod
    def from_json(cls, payload: str | None) -> "WizardState":
        if not payload:
            return cls()
        try:
            data = json.loads(payload)
        except (TypeError, ValueError):
            return cls()
        if not isinstance(data, dict):
            return cls()
        return cls(data)

    def assert_serializable(self) -> None:
        """Raise if the state cannot be JSON-serialized."""
        json.dumps(self._data, default=str)
