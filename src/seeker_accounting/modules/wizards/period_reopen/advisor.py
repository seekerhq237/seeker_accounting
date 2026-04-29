"""Advisor for the Period Reopen Wizard."""
from __future__ import annotations

from seeker_accounting.modules.wizards.period_reopen import state_keys as K
from seeker_accounting.platform.wizards import (
    AdvisorMessage,
    AdvisorSeverity,
    WizardAdvisor,
    WizardContext,
    WizardState,
)


def _pick_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    if state.get(K.KEY_PREVIOUS_STATUS) == "LOCKED":
        return [
            AdvisorMessage(
                severity=AdvisorSeverity.WARNING,
                title="Period is LOCKED",
                detail="Locked periods are typically frozen for tax/audit. Reopening should be exceptional.",
            )
        ]
    return []


def _reason_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    return [
        AdvisorMessage(
            severity=AdvisorSeverity.SUGGESTION,
            title="Be specific",
            detail="A good reason references the source document, the discovery date, and the corrective action planned.",
        )
    ]


def _reopen_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    return [
        AdvisorMessage(
            severity=AdvisorSeverity.INFO,
            title="Audit-trail enabled",
            detail="The reopen, the reason, and your user id will all be recorded.",
        )
    ]


def build_period_reopen_advisor() -> WizardAdvisor:
    advisor = WizardAdvisor(wizard_code="period_reopen")
    advisor.register("pick_period", _pick_rules)
    advisor.register("reason", _reason_rules)
    advisor.register("reopen", _reopen_rules)
    return advisor
