"""Advisor for the Stock Count Wizard."""
from __future__ import annotations

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
            title="Pick the right offset account",
            detail="Variances post against the offset account. Use a dedicated "
                   "'Inventory adjustments' expense or shrinkage account.",
        )
    ]


def _count_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    return [
        AdvisorMessage(
            severity=AdvisorSeverity.INFO,
            title="Blank means skip",
            detail="Leaving 'Counted qty' empty for an item skips it. Type 0 to "
                   "explicitly record that none were on hand.",
        )
    ]


def _variance_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    return [
        AdvisorMessage(
            severity=AdvisorSeverity.WARNING,
            title="Posted variances are visible in the GL",
            detail="Adjustments post to inventory and the offset account. "
                   "Confirm counts before continuing.",
        )
    ]


def build_stock_count_advisor() -> WizardAdvisor:
    advisor = WizardAdvisor(wizard_code="stock_count")
    advisor.register("setup", _setup_rules)
    advisor.register("count", _count_rules)
    advisor.register("variance", _variance_rules)
    return advisor
