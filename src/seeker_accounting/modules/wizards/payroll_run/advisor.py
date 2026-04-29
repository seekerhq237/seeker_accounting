"""Advisor rules for the Payroll Run Wizard."""
from __future__ import annotations

from decimal import Decimal

from seeker_accounting.modules.wizards.payroll_run import state_keys as K
from seeker_accounting.platform.wizards import (
    AdvisorMessage,
    AdvisorSeverity,
    WizardAdvisor,
    WizardContext,
    WizardState,
)


def _period_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    messages: list[AdvisorMessage] = []
    if not state.get(K.KEY_RUN_LABEL):
        messages.append(
            AdvisorMessage(
                severity=AdvisorSeverity.INFO,
                title="Pick a clear label",
                detail="Use a label like \u201cMonthly Payroll \u2014 May 2026\u201d for easy retrieval.",
            )
        )
    return messages


def _review_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    n = state.get(K.KEY_EMPLOYEE_COUNT, 0)
    if n == 0:
        return [
            AdvisorMessage(
                severity=AdvisorSeverity.BLOCKER,
                title="No employees included",
                detail="The run has no included employees. Approval and posting are blocked.",
            )
        ]
    try:
        net = Decimal(str(state.get(K.KEY_TOTAL_NET) or "0"))
    except Exception:  # noqa: BLE001
        net = Decimal("0")
    if net <= 0:
        return [
            AdvisorMessage(
                severity=AdvisorSeverity.WARNING,
                title="Net total is zero or negative",
                detail="Verify component definitions and employee compensation before approving.",
            )
        ]
    return [
        AdvisorMessage(
            severity=AdvisorSeverity.INFO,
            title=f"{n} employee(s) included",
            detail="Review the table to spot any unexpectedly excluded or zeroed employees.",
        )
    ]


def _approve_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    if state.get(K.KEY_RUN_STATUS) == "approved":
        return [
            AdvisorMessage(
                severity=AdvisorSeverity.INFO,
                title="Run is already approved",
                detail="Continue to post the run.",
            )
        ]
    return [
        AdvisorMessage(
            severity=AdvisorSeverity.SUGGESTION,
            title="Approval is final",
            detail="After approval the employee scope is frozen. Cancel and recreate if changes are needed.",
        )
    ]


def _post_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    if state.get(K.KEY_POSTED_JOURNAL_ENTRY_ID):
        return [
            AdvisorMessage(
                severity=AdvisorSeverity.INFO,
                title="Already posted",
                detail="Finish the wizard to record the outcome.",
            )
        ]
    return [
        AdvisorMessage(
            severity=AdvisorSeverity.WARNING,
            title="Posting date must be in an OPEN period",
            detail=(
                "If the chosen date falls in a CLOSED or LOCKED period, posting "
                "will fail. Adjust the posting date or reopen the period first."
            ),
        )
    ]


def build_payroll_run_advisor() -> WizardAdvisor:
    advisor = WizardAdvisor(wizard_code="payroll_run")
    advisor.register("period_and_calculate", _period_rules)
    advisor.register("review_employees", _review_rules)
    advisor.register("approve", _approve_rules)
    advisor.register("post", _post_rules)
    return advisor
