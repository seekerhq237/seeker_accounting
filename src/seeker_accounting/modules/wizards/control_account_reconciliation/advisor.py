"""Advisor for the Control Account Reconciliation wizard."""
from __future__ import annotations

from seeker_accounting.modules.reporting.dto.control_account_reconciliation_dto import (
    ControlAccountReconciliationReportDTO,
)
from seeker_accounting.modules.wizards.control_account_reconciliation import state_keys as K
from seeker_accounting.platform.wizards import (
    AdvisorMessage,
    AdvisorSeverity,
    WizardAdvisor,
    WizardContext,
    WizardState,
)


def _setup_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    return [
        AdvisorMessage(
            severity=AdvisorSeverity.INFO,
            title="Pick the right cut-off date",
            detail="Use the period-end date you want to reconcile (typically "
                   "the last day of a closed or closing period).",
        )
    ]


def _review_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    report = state.get(K.KEY_REPORT)
    if not isinstance(report, ControlAccountReconciliationReportDTO):
        return []
    messages: list[AdvisorMessage] = []
    for section in report.sections:
        if not section.account_mapped:
            messages.append(
                AdvisorMessage(
                    severity=AdvisorSeverity.WARNING,
                    title=f"{section.role_label} role not mapped",
                    detail="Configure the role under Account Role Mappings so future "
                           "reconciliations and posting flows can find the control account.",
                )
            )
            continue
        if section.gl_balance is None:
            messages.append(
                AdvisorMessage(
                    severity=AdvisorSeverity.WARNING,
                    title=f"{section.role_label}: GL balance unavailable",
                    detail="The mapped account could not be read. Verify the role mapping "
                           "still points to a valid, active account.",
                )
            )
            continue
        if not section.is_reconciled:
            messages.append(
                AdvisorMessage(
                    severity=AdvisorSeverity.WARNING,
                    title=f"{section.role_label} subledger does not match GL",
                    detail="Investigate manual journals against the control account, "
                           "unposted source documents, or allocations posted in a "
                           "different period.",
                )
            )
        else:
            messages.append(
                AdvisorMessage(
                    severity=AdvisorSeverity.INFO,
                    title=f"{section.role_label} reconciled",
                    detail="GL and subledger agree within the materiality tolerance.",
                )
            )
    return messages


def build_control_account_reconciliation_advisor() -> WizardAdvisor:
    advisor = WizardAdvisor(wizard_code="control_account_reconciliation")
    advisor.register("setup", _setup_rules)
    advisor.register("review", _review_rules)
    return advisor
