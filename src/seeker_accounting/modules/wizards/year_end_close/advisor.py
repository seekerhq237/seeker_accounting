"""Advisor for the Year-End Close Wizard."""
from __future__ import annotations

from seeker_accounting.modules.wizards.year_end_close import state_keys as K
from seeker_accounting.platform.wizards import (
    AdvisorMessage,
    AdvisorSeverity,
    WizardAdvisor,
    WizardContext,
    WizardState,
)


def _pick_year_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    msgs: list[AdvisorMessage] = []
    if not isinstance(state.get(K.KEY_FISCAL_YEAR_ID), int):
        msgs.append(
            AdvisorMessage(
                severity=AdvisorSeverity.INFO,
                title="Pick a fiscal year",
                detail="Only fiscal years that are not already CLOSED appear in the list.",
            )
        )
    return msgs


def _periods_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    msgs: list[AdvisorMessage] = []
    snapshot = state.get(K.KEY_PERIODS_SNAPSHOT) or []
    open_count = sum(1 for p in snapshot if p.get("status_code") == "OPEN")
    if open_count:
        msgs.append(
            AdvisorMessage(
                severity=AdvisorSeverity.WARNING,
                title=f"{open_count} period(s) still OPEN",
                detail=(
                    "OPEN periods cannot be locked or skipped. Close them through the "
                    "Fiscal Periods workspace before re-running this wizard."
                ),
            )
        )
    closed_count = sum(1 for p in snapshot if p.get("status_code") == "CLOSED")
    if closed_count and not state.get(K.KEY_LOCK_CLOSED_PERIODS, True):
        msgs.append(
            AdvisorMessage(
                severity=AdvisorSeverity.SUGGESTION,
                title="Consider locking CLOSED periods",
                detail=(
                    "Locking provides an extra guardrail against re-opening periods after "
                    "the year is closed."
                ),
            )
        )
    return msgs


def _confirm_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    return [
        AdvisorMessage(
            severity=AdvisorSeverity.INFO,
            title="Closing entries",
            detail=(
                "Make sure your closing entries (revenue/expense → retained earnings) "
                "are posted before closing the year. This wizard does not generate them."
            ),
        )
    ]


def build_year_end_close_advisor() -> WizardAdvisor:
    advisor = WizardAdvisor(wizard_code="year_end_close")
    advisor.register("pick_year", _pick_year_rules)
    advisor.register("periods_review", _periods_rules)
    advisor.register("confirm", _confirm_rules)
    return advisor
