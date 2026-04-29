"""Advisor for the Purchase Credit Note Wizard."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from seeker_accounting.modules.wizards.purchase_credit_note import state_keys as K
from seeker_accounting.platform.wizards import (
    AdvisorMessage,
    AdvisorSeverity,
    WizardAdvisor,
    WizardContext,
    WizardState,
)


def _header_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    msgs: list[AdvisorMessage] = []
    if not state.get(K.KEY_SOURCE_BILL_ID):
        msgs.append(
            AdvisorMessage(
                severity=AdvisorSeverity.SUGGESTION,
                title="Link to a source bill",
                detail="Linking the credit note to the original supplier bill keeps AP aging clean and supports automated allocations.",
            )
        )
    if not state.get(K.KEY_SUPPLIER_CREDIT_REFERENCE):
        msgs.append(
            AdvisorMessage(
                severity=AdvisorSeverity.SUGGESTION,
                title="Capture the supplier reference",
                detail="The supplier's own credit-memo number is recommended for audit trail and three-way matching later.",
            )
        )
    if not state.get(K.KEY_REASON_TEXT):
        msgs.append(
            AdvisorMessage(
                severity=AdvisorSeverity.SUGGESTION,
                title="Document the reason",
                detail="A reason text is recommended for audit trail (e.g. 'goods returned', 'pricing correction').",
            )
        )
    return msgs


def _lines_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    lines = state.get(K.KEY_LINES) or []
    if not lines:
        return []
    total = Decimal(0)
    for ln in lines:
        try:
            total += Decimal(str(ln.get("quantity") or "0")) * Decimal(str(ln.get("unit_cost") or "0"))
        except (InvalidOperation, ValueError):
            continue
    if total == 0:
        return [
            AdvisorMessage(
                severity=AdvisorSeverity.WARNING,
                title="Zero-value credit note",
                detail="The subtotal is zero. Confirm this is intentional.",
            )
        ]
    return []


def _confirm_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    if state.get(K.KEY_POST_NOW):
        return [
            AdvisorMessage(
                severity=AdvisorSeverity.WARNING,
                title="Posting immediately",
                detail="Posted credit notes are immutable and adjust the supplier control account. Only post when verified.",
            )
        ]
    return [
        AdvisorMessage(
            severity=AdvisorSeverity.INFO,
            title="Draft only",
            detail="The credit note will be saved as a draft; you can review and post later from the Purchases workspace.",
        )
    ]


def build_purchase_credit_note_advisor() -> WizardAdvisor:
    advisor = WizardAdvisor(wizard_code="purchase_credit_note")
    advisor.register("header", _header_rules)
    advisor.register("lines", _lines_rules)
    advisor.register("confirm", _confirm_rules)
    return advisor
