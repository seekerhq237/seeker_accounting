"""Assistant Engine — the wizard's "expert in the shadows".

Per ``docs/Wizards.md``, every wizard gets shared assistive capabilities:

1. Context sniffing
2. Prerequisite detection
3. Safe defaults
4. Risk & anomaly flags
5. Plain-language explanations

This module ships a deterministic, **rules-only** v1 implementation — fully
offline, fully explainable, and aligned with the project's accounting-correct
discipline. Per-wizard advisors register messages keyed by step. The host
dialog displays them in a side pane.

LLM hooks may be added later as an optional enrichment without changing
this contract.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from seeker_accounting.platform.wizards.context import WizardContext
    from seeker_accounting.platform.wizards.state import WizardState


class AdvisorSeverity(str, Enum):
    INFO = "info"
    SUGGESTION = "suggestion"
    WARNING = "warning"
    BLOCKER = "blocker"


@dataclass(slots=True, frozen=True)
class AdvisorMessage:
    """A single observation surfaced by the advisor for a step."""

    severity: AdvisorSeverity
    title: str
    detail: str = ""
    action_label: str | None = None
    #: Optional callable invoked when the user clicks the action chip.
    action: Callable[[], None] | None = None


AdvisorRule = Callable[
    ["WizardContext", "WizardState"],
    list[AdvisorMessage] | AdvisorMessage | None,
]


@dataclass(slots=True)
class WizardAdvisor:
    """Per-wizard rule pack.

    Register rules keyed by step ``key``. Each rule receives the live context
    and current state and returns zero or more ``AdvisorMessage`` instances.
    Rules MUST be side-effect free — they are also called for previewing.
    """

    wizard_code: str
    rules_by_step: dict[str, list[AdvisorRule]] = field(default_factory=dict)

    def register(self, step_key: str, rule: AdvisorRule) -> None:
        self.rules_by_step.setdefault(step_key, []).append(rule)


class AssistantEngine:
    """Runs a wizard's advisor rules and returns a flattened message list.

    The engine is intentionally thin: it traps individual rule errors so a
    single buggy rule cannot bring down the wizard, and it sorts messages by
    severity (BLOCKER first) for predictable UI rendering.
    """

    _SEVERITY_ORDER = {
        AdvisorSeverity.BLOCKER: 0,
        AdvisorSeverity.WARNING: 1,
        AdvisorSeverity.SUGGESTION: 2,
        AdvisorSeverity.INFO: 3,
    }

    def evaluate_step(
        self,
        advisor: WizardAdvisor | None,
        step_key: str,
        context: "WizardContext",
        state: "WizardState",
    ) -> list[AdvisorMessage]:
        if advisor is None:
            return []
        rules = advisor.rules_by_step.get(step_key, [])
        messages: list[AdvisorMessage] = []
        for rule in rules:
            try:
                produced = rule(context, state)
            except Exception:  # noqa: BLE001
                # Defensive: an advisor rule must never break the wizard.
                continue
            if produced is None:
                continue
            if isinstance(produced, AdvisorMessage):
                messages.append(produced)
                continue
            messages.extend(m for m in produced if isinstance(m, AdvisorMessage))
        messages.sort(key=lambda m: self._SEVERITY_ORDER.get(m.severity, 9))
        return messages

    def has_blockers(self, messages: list[AdvisorMessage]) -> bool:
        return any(m.severity is AdvisorSeverity.BLOCKER for m in messages)
