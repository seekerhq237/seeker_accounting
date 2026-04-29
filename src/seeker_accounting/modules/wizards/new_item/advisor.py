"""Advisor for the New Item Wizard."""
from __future__ import annotations

from seeker_accounting.modules.wizards.new_item import state_keys as K
from seeker_accounting.platform.wizards import (
    AdvisorMessage,
    AdvisorSeverity,
    WizardAdvisor,
    WizardContext,
    WizardState,
)


def _identity_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    msgs: list[AdvisorMessage] = []
    type_code = state.get(K.KEY_ITEM_TYPE_CODE)
    if type_code == "stock":
        msgs.append(
            AdvisorMessage(
                severity=AdvisorSeverity.INFO,
                title="Stock item",
                detail="Stock items track quantity-on-hand and require inventory + COGS accounts.",
            )
        )
    elif type_code == "service":
        msgs.append(
            AdvisorMessage(
                severity=AdvisorSeverity.INFO,
                title="Service item",
                detail="Service items don't track inventory; only revenue and (optionally) expense accounts apply.",
            )
        )
    return msgs


def _classification_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    msgs: list[AdvisorMessage] = []
    if state.get(K.KEY_ITEM_TYPE_CODE) == "stock" and state.get(K.KEY_INVENTORY_COST_METHOD_CODE) is None:
        msgs.append(
            AdvisorMessage(
                severity=AdvisorSeverity.WARNING,
                title="Cost method required",
                detail="Stock items must use a cost method (weighted average) for COGS posting.",
            )
        )
    return msgs


def _accounts_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    msgs: list[AdvisorMessage] = []
    type_code = state.get(K.KEY_ITEM_TYPE_CODE)
    if not state.get(K.KEY_REVENUE_ACCOUNT_ID):
        msgs.append(
            AdvisorMessage(
                severity=AdvisorSeverity.SUGGESTION,
                title="No revenue account",
                detail="Without a default revenue account, sales lines for this item won't auto-pick a GL.",
            )
        )
    if type_code == "stock" and not state.get(K.KEY_INVENTORY_ACCOUNT_ID):
        msgs.append(
            AdvisorMessage(
                severity=AdvisorSeverity.WARNING,
                title="Inventory account missing",
                detail="Stock items require an inventory asset account.",
            )
        )
    return msgs


def build_new_item_advisor() -> WizardAdvisor:
    advisor = WizardAdvisor(wizard_code="new_item")
    advisor.register("identity", _identity_rules)
    advisor.register("classification", _classification_rules)
    advisor.register("accounts", _accounts_rules)
    return advisor
