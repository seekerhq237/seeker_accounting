"""Advisor for the Journal Reversal Wizard."""
from __future__ import annotations

from seeker_accounting.platform.wizards import (
    AdvisorMessage,
    AdvisorSeverity,
    WizardAdvisor,
    WizardContext,
    WizardState,
)


def _pick_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    return [
        AdvisorMessage(
            severity=AdvisorSeverity.INFO,
            title="Pick the originating entry, not a previous reversal",
            detail="Reversals of reversals are not permitted. The list already "
                   "excludes them.",
        )
    ]


def _details_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    return [
        AdvisorMessage(
            severity=AdvisorSeverity.WARNING,
            title="A reason is required",
            detail="Reversals are auditable events. Be specific so reviewers "
                   "understand why this entry was undone.",
        )
    ]


def build_journal_reversal_advisor() -> WizardAdvisor:
    advisor = WizardAdvisor(wizard_code="journal_reversal")
    advisor.register("pick", _pick_rules)
    advisor.register("details", _details_rules)
    return advisor
