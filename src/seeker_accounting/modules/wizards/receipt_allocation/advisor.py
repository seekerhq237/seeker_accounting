"""Advisor for Receipt Allocation Wizard."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from seeker_accounting.modules.wizards.receipt_allocation import state_keys as K
from seeker_accounting.platform.wizards import (
    AdvisorMessage,
    AdvisorSeverity,
    WizardAdvisor,
    WizardContext,
    WizardState,
)


def _header_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    msgs: list[AdvisorMessage] = []
    receipt_cur = state.get(K.KEY_CURRENCY_CODE)
    acct_cur = state.get(K.KEY_FINANCIAL_ACCOUNT_CURRENCY)
    if receipt_cur and acct_cur and receipt_cur != acct_cur:
        msgs.append(
            AdvisorMessage(
                severity=AdvisorSeverity.WARNING,
                title="Currency mismatch",
                detail=f"Receipt currency {receipt_cur} differs from the deposit account currency {acct_cur}. Make sure exchange rate handling is intentional.",
            )
        )
    return msgs


def _allocate_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    try:
        amount = Decimal(str(state.get(K.KEY_AMOUNT_RECEIVED) or "0"))
        allocated = Decimal(str(state.get(K.KEY_TOTAL_ALLOCATED) or "0"))
    except (InvalidOperation, ValueError):
        return []
    if allocated < amount:
        diff = amount - allocated
        return [
            AdvisorMessage(
                severity=AdvisorSeverity.SUGGESTION,
                title=f"Unapplied amount: {diff:,.2f}",
                detail="The remainder will sit on the customer as unapplied cash. That can be intentional (overpayment) or you may want to fully allocate.",
            )
        ]
    if allocated == amount:
        return [
            AdvisorMessage(
                severity=AdvisorSeverity.INFO,
                title="Fully allocated",
                detail="The receipt amount is fully applied to invoices.",
            )
        ]
    return []


def _confirm_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    if state.get(K.KEY_POST_NOW):
        return [
            AdvisorMessage(
                severity=AdvisorSeverity.WARNING,
                title="Posting requires open period",
                detail="Posting will fail if the receipt date falls in a closed or locked fiscal period.",
            )
        ]
    return [
        AdvisorMessage(
            severity=AdvisorSeverity.INFO,
            title="Draft only",
            detail="The receipt will be saved as a draft. You can post it later from the Receipts page.",
        )
    ]


def build_receipt_allocation_advisor() -> WizardAdvisor:
    advisor = WizardAdvisor(wizard_code="receipt_allocation")
    advisor.register("header", _header_rules)
    advisor.register("allocate", _allocate_rules)
    advisor.register("confirm", _confirm_rules)
    return advisor
