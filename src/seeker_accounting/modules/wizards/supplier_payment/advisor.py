"""Advisor for Supplier Payment Wizard."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from seeker_accounting.modules.wizards.supplier_payment import state_keys as K
from seeker_accounting.platform.wizards import (
    AdvisorMessage,
    AdvisorSeverity,
    WizardAdvisor,
    WizardContext,
    WizardState,
)


def _header_rules(ctx, state):
    msgs: list[AdvisorMessage] = []
    pay_cur = state.get(K.KEY_CURRENCY_CODE)
    acct_cur = state.get(K.KEY_FINANCIAL_ACCOUNT_CURRENCY)
    if pay_cur and acct_cur and pay_cur != acct_cur:
        msgs.append(
            AdvisorMessage(
                severity=AdvisorSeverity.WARNING,
                title="Currency mismatch",
                detail=f"Payment currency {pay_cur} differs from the source account currency {acct_cur}.",
            )
        )
    return msgs


def _allocate_rules(ctx, state):
    try:
        amount = Decimal(str(state.get(K.KEY_AMOUNT_PAID) or "0"))
        allocated = Decimal(str(state.get(K.KEY_TOTAL_ALLOCATED) or "0"))
    except (InvalidOperation, ValueError):
        return []
    if allocated < amount:
        diff = amount - allocated
        return [
            AdvisorMessage(
                severity=AdvisorSeverity.SUGGESTION,
                title=f"Unapplied amount: {diff:,.2f}",
                detail="Remainder will sit on the supplier as on-account credit.",
            )
        ]
    if allocated == amount:
        return [
            AdvisorMessage(
                severity=AdvisorSeverity.INFO,
                title="Fully allocated",
                detail="The payment is fully applied to bills.",
            )
        ]
    return []


def _confirm_rules(ctx, state):
    if state.get(K.KEY_POST_NOW):
        return [
            AdvisorMessage(
                severity=AdvisorSeverity.WARNING,
                title="Posting requires open period",
                detail="Posting will fail if the payment date falls in a closed or locked fiscal period.",
            )
        ]
    return [
        AdvisorMessage(
            severity=AdvisorSeverity.INFO,
            title="Draft only",
            detail="The payment will be saved as a draft. Post it later from the Payments page.",
        )
    ]


def build_supplier_payment_advisor() -> WizardAdvisor:
    advisor = WizardAdvisor(wizard_code="supplier_payment")
    advisor.register("header", _header_rules)
    advisor.register("allocate", _allocate_rules)
    advisor.register("confirm", _confirm_rules)
    return advisor
