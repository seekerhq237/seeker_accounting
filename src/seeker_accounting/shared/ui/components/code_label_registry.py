"""CodeLabelRegistry — centralized enum-code → display-label map.

Every enum value displayed in payroll (and other) UI must flow through
this registry instead of being interpolated as a raw code. Missing keys
log a warning (not a silent fallback) so unmapped codes are caught in
QA, not in production. Display fallback returns a Title-Cased version
of the code so the UI never blows up.

Categories follow the persistence-side enum names, e.g.
``payroll_run_status``, ``payroll_component_type``,
``payroll_remittance_authority``, ``severity``.

This module is a pure UI primitive — no domain imports, no service
imports. Feature modules register their own labels at startup.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from threading import RLock
from typing import Final

_log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CodeLabel:
    """A single registry entry."""
    code: str
    label: str
    tooltip: str = ""
    family: str | None = None  # optional StatusChip family / SeverityPill severity


@dataclass
class _RegistryStore:
    entries: dict[tuple[str, str], CodeLabel] = field(default_factory=dict)
    missing_seen: set[tuple[str, str]] = field(default_factory=set)


class CodeLabelRegistry:
    """Process-wide registry. Threadsafe registration + lookup."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._store = _RegistryStore()

    def register(
        self,
        category: str,
        code: str,
        label: str,
        *,
        tooltip: str = "",
        family: str | None = None,
        overwrite: bool = False,
    ) -> None:
        key = (category, _normalize(code))
        with self._lock:
            if not overwrite and key in self._store.entries:
                return
            self._store.entries[key] = CodeLabel(
                code=code, label=label, tooltip=tooltip, family=family
            )

    def register_many(
        self, category: str, mapping: dict[str, str | tuple[str, str] | tuple[str, str, str]]
    ) -> None:
        """Bulk register: ``mapping[code] = label`` or ``(label, tooltip)`` or
        ``(label, tooltip, family)``."""
        for code, value in mapping.items():
            if isinstance(value, str):
                self.register(category, code, value)
            elif len(value) == 2:
                self.register(category, code, value[0], tooltip=value[1])
            elif len(value) == 3:
                self.register(
                    category, code, value[0], tooltip=value[1], family=value[2]
                )
            else:
                raise ValueError(
                    f"register_many: unexpected value shape for {category}:{code}"
                )

    def get(self, category: str, code: str | None) -> CodeLabel:
        if not code:
            return CodeLabel(code="", label="\u2014")
        key = (category, _normalize(code))
        with self._lock:
            entry = self._store.entries.get(key)
            if entry is not None:
                return entry
            if key not in self._store.missing_seen:
                self._store.missing_seen.add(key)
                _log.warning(
                    "CodeLabelRegistry: unmapped code %s:%s — using fallback label",
                    category,
                    code,
                )
        return CodeLabel(code=code, label=_fallback_label(code))

    def label(self, category: str, code: str | None) -> str:
        return self.get(category, code).label

    def tooltip(self, category: str, code: str | None) -> str:
        return self.get(category, code).tooltip

    def family(self, category: str, code: str | None) -> str | None:
        return self.get(category, code).family

    # --- introspection / testing --------------------------------------

    def has(self, category: str, code: str) -> bool:
        with self._lock:
            return (category, _normalize(code)) in self._store.entries

    def categories(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted({cat for cat, _ in self._store.entries.keys()}))

    def codes(self, category: str) -> tuple[str, ...]:
        with self._lock:
            return tuple(
                entry.code
                for (cat, _), entry in self._store.entries.items()
                if cat == category
            )

    def clear(self) -> None:
        """Used only by tests."""
        with self._lock:
            self._store = _RegistryStore()


def _normalize(code: str) -> str:
    out = code.strip().lower()
    for ch in (" ", "-"):
        out = out.replace(ch, "_")
    while "__" in out:
        out = out.replace("__", "_")
    return out


def _fallback_label(code: str) -> str:
    cleaned = code.replace("_", " ").replace("-", " ").strip()
    if not cleaned:
        return "\u2014"
    return " ".join(part[:1].upper() + part[1:].lower() for part in cleaned.split() if part)


# Process-wide singleton.
CODE_LABELS: Final[CodeLabelRegistry] = CodeLabelRegistry()


# ── Built-in seed: severity codes (used by SeverityPill / InlineIssueBand)
CODE_LABELS.register_many(
    "severity",
    {
        "blocker": ("Blocker", "Must be resolved before this action can proceed.", "blocker"),
        "error": ("Error", "Invalid input or rule failure.", "error"),
        "warning": ("Warning", "Allowed, but worth reviewing.", "warning"),
        "info": ("Info", "Informational note.", "info"),
        "notice": ("Notice", "Low-priority note.", "notice"),
    },
)
