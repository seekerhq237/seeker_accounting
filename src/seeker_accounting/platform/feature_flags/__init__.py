"""Feature flag service.

Lightweight, env-driven, additive. Pages and shell consult this service
to decide whether to surface preview UIs (e.g. the Payroll Workbench
introduced by Phase 2 of the payroll UX remediation plan).

Flag values are read from process environment variables at construction
time; truthy values are ``"1"``, ``"true"``, ``"yes"``, ``"on"``
(case-insensitive). Anything else — including unset — is treated as
disabled.

The service intentionally has no database dependency: rolling the
preview out per-company belongs to a follow-up slice.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final, Mapping

# ── Known flags ───────────────────────────────────────────────────────

#: Phase 2 — single Payroll Workbench shell.
FLAG_PAYROLL_WORKBENCH: Final = "payroll_workbench"


_TRUTHY: Final = frozenset({"1", "true", "yes", "on", "enable", "enabled"})


@dataclass(frozen=True, slots=True)
class FeatureFlag:
    """Static descriptor for a known flag."""

    code: str
    env_var: str
    description: str
    default: bool = False


_REGISTRY: Final[Mapping[str, FeatureFlag]] = {
    FLAG_PAYROLL_WORKBENCH: FeatureFlag(
        code=FLAG_PAYROLL_WORKBENCH,
        env_var="SEEKER_PAYROLL_WORKBENCH",
        description=(
            "Enable the Phase 2 Payroll Workbench (single sidebar entry, "
            "left-rail navigation, dashboard, deep-linkable panes). The "
            "legacy four payroll pages remain reachable when this flag "
            "is enabled."
        ),
        default=False,
    ),
}


class FeatureFlagService:
    """Resolves feature flags from a frozen environment snapshot.

    Snapshot semantics keep the result stable for the lifetime of an app
    session; tests can pass a fresh ``env`` mapping to flip flags
    deterministically.
    """

    def __init__(self, env: Mapping[str, str] | None = None) -> None:
        self._env = dict(env if env is not None else os.environ)

    # ── Queries ───────────────────────────────────────────────────────

    def is_enabled(self, code: str) -> bool:
        flag = _REGISTRY.get(code)
        if flag is None:
            return False
        raw = self._env.get(flag.env_var)
        if raw is None:
            return flag.default
        return raw.strip().lower() in _TRUTHY

    def all_enabled(self) -> tuple[str, ...]:
        return tuple(code for code in _REGISTRY if self.is_enabled(code))

    @staticmethod
    def known_flags() -> tuple[FeatureFlag, ...]:
        return tuple(_REGISTRY.values())
