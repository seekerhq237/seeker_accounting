"""Advisor rules for the Month-End Close Wizard."""
from __future__ import annotations

from seeker_accounting.modules.wizards.month_end_close import state_keys as K
from seeker_accounting.platform.wizards import (
    AdvisorMessage,
    AdvisorSeverity,
    WizardAdvisor,
    WizardContext,
    WizardState,
)


def _period_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    if state.get(K.KEY_PERIOD_ID) is None:
        return [
            AdvisorMessage(
                severity=AdvisorSeverity.INFO,
                title="Pick the period",
                detail="Closing flows month-by-month; select the earliest OPEN period first.",
            )
        ]
    return []


def _drafts_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    n = state.get(K.KEY_DRAFTS_COUNT, 0)
    if n == 0:
        return [
            AdvisorMessage(
                severity=AdvisorSeverity.INFO,
                title="No unposted drafts",
                detail="Nothing to chase up before close.",
            )
        ]
    return [
        AdvisorMessage(
            severity=AdvisorSeverity.WARNING,
            title=f"{n} draft(s) in this period",
            detail=(
                "Drafts left unposted at close will not appear in this period's "
                "results. Post them or delete them before closing if they belong "
                "in this period."
            ),
        )
    ]


def _recon_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    gaps: list[str] = []
    if not state.get(K.KEY_RECON_BANK_ACK):
        gaps.append("bank/cash")
    if not state.get(K.KEY_RECON_AR_ACK):
        gaps.append("AR control")
    if not state.get(K.KEY_RECON_AP_ACK):
        gaps.append("AP control")
    if not gaps:
        return [
            AdvisorMessage(
                severity=AdvisorSeverity.INFO,
                title="Reconciliations confirmed",
                detail="All checklist items are checked.",
            )
        ]
    return [
        AdvisorMessage(
            severity=AdvisorSeverity.SUGGESTION,
            title="Unconfirmed reconciliations",
            detail=(
                "Outstanding items: " + ", ".join(gaps) + ". You can still close, "
                "but discrepancies discovered later may require a period reopen."
            ),
        )
    ]


def _close_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    messages: list[AdvisorMessage] = []
    if state.get(K.KEY_DRAFTS_COUNT, 0) > 0:
        messages.append(
            AdvisorMessage(
                severity=AdvisorSeverity.WARNING,
                title="Drafts will not be posted",
                detail="The wizard does not auto-post drafts. They remain in DRAFT after close.",
            )
        )
    if not state.get(K.KEY_CLOSE_CONFIRMED):
        messages.append(
            AdvisorMessage(
                severity=AdvisorSeverity.BLOCKER,
                title="Confirmation required",
                detail="Tick the confirmation checkbox to enable Finish.",
            )
        )
    return messages


def build_month_end_close_advisor() -> WizardAdvisor:
    advisor = WizardAdvisor(wizard_code="month_end_close")
    advisor.register("period_selection", _period_rules)
    advisor.register("drafts_check", _drafts_rules)
    advisor.register("reconciliation_check", _recon_rules)
    advisor.register("close", _close_rules)
    return advisor
