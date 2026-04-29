"""Advisor for the Bank & Cash Setup Wizard."""
from __future__ import annotations

from seeker_accounting.modules.wizards.bank_cash_setup import state_keys as K
from seeker_accounting.platform.wizards import (
    AdvisorMessage,
    AdvisorSeverity,
    WizardAdvisor,
    WizardContext,
    WizardState,
)


def _type_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    return [
        AdvisorMessage(
            severity=AdvisorSeverity.INFO,
            title="Each financial account is single-currency",
            detail="If you operate in multiple currencies, create one financial account per currency for the same bank.",
        )
    ]


def _details_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    msgs: list[AdvisorMessage] = []
    if state.get(K.KEY_ACCOUNT_TYPE_CODE) == "bank" and not state.get(K.KEY_BANK_NAME):
        msgs.append(
            AdvisorMessage(
                severity=AdvisorSeverity.SUGGESTION,
                title="Capture the bank name",
                detail="Bank name and account number help with statement imports and reconciliation later.",
            )
        )
    if state.get(K.KEY_ACCOUNT_TYPE_CODE) == "petty_cash":
        msgs.append(
            AdvisorMessage(
                severity=AdvisorSeverity.INFO,
                title="Petty cash float",
                detail="Plan to replenish petty cash from a bank account on a recurring basis; transfers go through Treasury.",
            )
        )
    return msgs


def _confirm_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    return [
        AdvisorMessage(
            severity=AdvisorSeverity.INFO,
            title="Linked GL account",
            detail="The GL account you selected becomes the cash/bank ledger for this financial account. Postings to this account flow through Treasury.",
        )
    ]


def build_bank_cash_setup_advisor() -> WizardAdvisor:
    advisor = WizardAdvisor(wizard_code="bank_cash_setup")
    advisor.register("type", _type_rules)
    advisor.register("details", _details_rules)
    advisor.register("confirm", _confirm_rules)
    return advisor
