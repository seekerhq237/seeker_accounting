"""Advisor for the Depreciation Run Wizard."""
from __future__ import annotations

from datetime import date

from seeker_accounting.modules.wizards.depreciation_run import state_keys as K
from seeker_accounting.platform.wizards import (
    AdvisorMessage,
    AdvisorSeverity,
    WizardAdvisor,
    WizardContext,
    WizardState,
)


def _create_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    raw = state.get(K.KEY_PERIOD_END_DATE)
    if not raw:
        return []
    try:
        end = date.fromisoformat(str(raw))
    except ValueError:
        return []
    if end.day not in (28, 29, 30, 31):
        return [
            AdvisorMessage(
                severity=AdvisorSeverity.SUGGESTION,
                title="Use end-of-month",
                detail="Depreciation is usually charged through the last day of the month for clean reporting.",
            )
        ]
    return []


def _preview_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    if not state.get(K.KEY_ASSET_COUNT):
        return [
            AdvisorMessage(
                severity=AdvisorSeverity.BLOCKER,
                title="No eligible assets",
                detail="Posting is blocked. Activate assets and ensure they have depreciation methods.",
            )
        ]
    return [
        AdvisorMessage(
            severity=AdvisorSeverity.INFO,
            title="Review outliers",
            detail="Spot any line that looks unusually large compared to the asset's monthly base.",
        )
    ]


def _post_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    return [
        AdvisorMessage(
            severity=AdvisorSeverity.WARNING,
            title="Posting period must be open",
            detail="If the period-end date falls in a CLOSED or LOCKED period, posting will fail.",
        )
    ]


def build_depreciation_run_advisor() -> WizardAdvisor:
    advisor = WizardAdvisor(wizard_code="depreciation_run")
    advisor.register("create_run", _create_rules)
    advisor.register("preview", _preview_rules)
    advisor.register("post", _post_rules)
    return advisor
