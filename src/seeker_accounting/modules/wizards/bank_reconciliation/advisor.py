"""Advisor for the Bank Reconciliation Wizard."""
from __future__ import annotations

from seeker_accounting.modules.wizards.bank_reconciliation import state_keys as K
from seeker_accounting.platform.wizards import (
    AdvisorMessage,
    AdvisorSeverity,
    WizardAdvisor,
    WizardContext,
    WizardState,
)


def _statement_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    return [
        AdvisorMessage(
            severity=AdvisorSeverity.SUGGESTION,
            title="Use the official statement",
            detail="Enter the closing balance exactly as printed on the bank statement \u2014 cents matter.",
        )
    ]


def _summary_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    unmatched = state.get(K.KEY_UNMATCHED_COUNT, 0)
    if unmatched and unmatched > 0:
        return [
            AdvisorMessage(
                severity=AdvisorSeverity.WARNING,
                title=f"{unmatched} line(s) still unmatched",
                detail="You can finalize anyway, but unmatched lines remain visible for follow-up.",
            )
        ]
    return [
        AdvisorMessage(
            severity=AdvisorSeverity.INFO,
            title="All statement lines matched",
            detail="Safe to finalize.",
        )
    ]


def _finalize_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    return [
        AdvisorMessage(
            severity=AdvisorSeverity.INFO,
            title="Completion is logged",
            detail="The completion timestamp and your user id will be recorded on the session.",
        )
    ]


def build_bank_reconciliation_advisor() -> WizardAdvisor:
    advisor = WizardAdvisor(wizard_code="bank_reconciliation")
    advisor.register("statement", _statement_rules)
    advisor.register("match_summary", _summary_rules)
    advisor.register("finalize", _finalize_rules)
    return advisor
