"""Advisor for the Opening Balances Wizard."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from seeker_accounting.modules.wizards.opening_balances import state_keys as K
from seeker_accounting.platform.wizards import (
    AdvisorMessage,
    AdvisorSeverity,
    WizardAdvisor,
    WizardContext,
    WizardState,
)


def _header_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    return [
        AdvisorMessage(
            severity=AdvisorSeverity.INFO,
            title="Opening date",
            detail="The opening date should be the day BEFORE the first operational period (e.g. 2025-12-31 for FY 2026).",
        )
    ]


def _lines_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    msgs: list[AdvisorMessage] = []
    lines = state.get(K.KEY_LINES) or []
    valid = [ln for ln in lines if ln.get("account_id")]
    if not valid:
        return msgs
    dr_total = Decimal(0)
    cr_total = Decimal(0)
    for ln in valid:
        try:
            dr_total += Decimal(str(ln.get("debit_amount") or "0"))
            cr_total += Decimal(str(ln.get("credit_amount") or "0"))
        except (InvalidOperation, ValueError):
            continue
    if dr_total != cr_total:
        msgs.append(
            AdvisorMessage(
                severity=AdvisorSeverity.WARNING,
                title="Out of balance",
                detail=f"Debits {dr_total:.2f} \u2260 credits {cr_total:.2f}. The entry won't save until balanced.",
            )
        )
    if len(valid) < 5:
        msgs.append(
            AdvisorMessage(
                severity=AdvisorSeverity.SUGGESTION,
                title="Capture all opening accounts",
                detail="Most opening trial balances span dozens of accounts (cash, AR, AP, equity, retained earnings).",
            )
        )
    return msgs


def _confirm_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    return [
        AdvisorMessage(
            severity=AdvisorSeverity.WARNING,
            title="Draft only",
            detail="The wizard creates a DRAFT entry. Review carefully and post from the Journals workspace once verified.",
        )
    ]


def build_opening_balances_advisor() -> WizardAdvisor:
    advisor = WizardAdvisor(wizard_code="opening_balances")
    advisor.register("header", _header_rules)
    advisor.register("lines", _lines_rules)
    advisor.register("confirm", _confirm_rules)
    return advisor
