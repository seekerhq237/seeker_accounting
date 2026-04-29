"""Advisor for the FX Revaluation Wizard."""
from __future__ import annotations

from seeker_accounting.modules.wizards.fx_revaluation import state_keys as K
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
            title="Pick the right accounts",
            detail="Use distinct unrealized gain and loss accounts so the impact is clear "
                   "in the income statement.",
        )
    ]


def _lines_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    msgs: list[AdvisorMessage] = []
    rows = state.get(K.KEY_LINES) or ()
    if not rows:
        return msgs
    msgs.append(
        AdvisorMessage(
            severity=AdvisorSeverity.INFO,
            title="Sign convention",
            detail="Use positive amounts for accounts with debit-side balances "
                   "(receivables, cash) and negative amounts for credit-side "
                   "balances (payables). Delta = target − current.",
        )
    )
    return msgs


def _confirm_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    return [
        AdvisorMessage(
            severity=AdvisorSeverity.WARNING,
            title="This posts immediately",
            detail="The revaluation is posted as a single balanced journal entry "
                   "as soon as you click Finish.",
        )
    ]


def build_fx_revaluation_advisor() -> WizardAdvisor:
    advisor = WizardAdvisor(wizard_code="fx_revaluation")
    advisor.register("setup", _setup_rules)
    advisor.register("lines", _lines_rules)
    advisor.register("confirm", _confirm_rules)
    return advisor
