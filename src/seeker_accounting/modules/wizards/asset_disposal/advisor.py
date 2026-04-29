"""Advisor for the Asset Disposal Wizard."""
from __future__ import annotations

from decimal import Decimal

from seeker_accounting.modules.wizards.asset_disposal import state_keys as K
from seeker_accounting.platform.wizards import (
    AdvisorMessage,
    AdvisorSeverity,
    WizardAdvisor,
    WizardContext,
    WizardState,
)


def _pick_asset_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    msgs: list[AdvisorMessage] = []
    if not isinstance(state.get(K.KEY_ASSET_ID), int):
        msgs.append(
            AdvisorMessage(
                severity=AdvisorSeverity.INFO,
                title="Pick an eligible asset",
                detail="Only assets in 'active' or 'fully_depreciated' status can be disposed.",
            )
        )
    return msgs


def _details_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    msgs: list[AdvisorMessage] = []
    amount = state.get(K.KEY_DISPOSAL_AMOUNT)
    if isinstance(amount, Decimal) and amount == Decimal("0"):
        msgs.append(
            AdvisorMessage(
                severity=AdvisorSeverity.INFO,
                title="Zero proceeds (scrap)",
                detail="Posting a scrap disposal will write a loss equal to the asset's net book value.",
            )
        )
    return msgs


def _confirm_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    return [
        AdvisorMessage(
            severity=AdvisorSeverity.WARNING,
            title="Disposal is final",
            detail="Disposing posts a journal entry and changes the asset status to 'disposed'. "
                   "The asset can no longer be edited or depreciated through normal flows.",
        )
    ]


def build_asset_disposal_advisor() -> WizardAdvisor:
    advisor = WizardAdvisor(wizard_code="asset_disposal")
    advisor.register("pick_asset", _pick_asset_rules)
    advisor.register("disposal_details", _details_rules)
    advisor.register("confirm", _confirm_rules)
    return advisor
