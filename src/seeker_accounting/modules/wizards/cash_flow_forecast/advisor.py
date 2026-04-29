"""Advisor for the Cash Flow Forecast wizard."""
from __future__ import annotations

from decimal import Decimal

from seeker_accounting.modules.reporting.dto.cash_flow_forecast_dto import (
    CashFlowForecastDTO,
)
from seeker_accounting.modules.wizards.cash_flow_forecast import state_keys as K
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
            title="Forecast scope",
            detail="The forecast uses posted-only cash balances plus open AR/AP "
                   "documents grouped by their due date. Unposted drafts are "
                   "ignored.",
        )
    ]


def _review_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    forecast = state.get(K.KEY_FORECAST)
    if not isinstance(forecast, CashFlowForecastDTO):
        return []
    messages: list[AdvisorMessage] = []
    if forecast.cash_account_count == 0:
        messages.append(
            AdvisorMessage(
                severity=AdvisorSeverity.WARNING,
                title="No cash/bank accounts configured",
                detail="Set up at least one bank or cash financial account so "
                       "the opening balance is meaningful.",
            )
        )
    if forecast.has_negative_bucket:
        messages.append(
            AdvisorMessage(
                severity=AdvisorSeverity.WARNING,
                title="Cash position turns negative",
                detail="At least one projected bucket closes below zero. "
                       "Consider accelerating collections or rescheduling payments.",
            )
        )
    if forecast.buckets and forecast.buckets[0].is_past_due:
        past_due = forecast.buckets[0]
        if past_due.expected_payments > Decimal("0"):
            messages.append(
                AdvisorMessage(
                    severity=AdvisorSeverity.WARNING,
                    title="Past-due payables present",
                    detail=f"{past_due.payments_document_count} supplier "
                           "document(s) are already past due.",
                )
            )
        if past_due.expected_receipts > Decimal("0"):
            messages.append(
                AdvisorMessage(
                    severity=AdvisorSeverity.INFO,
                    title="Past-due receivables present",
                    detail=f"{past_due.receipts_document_count} customer "
                           "document(s) are already past due — chase them.",
                )
            )
    if not messages:
        messages.append(
            AdvisorMessage(
                severity=AdvisorSeverity.INFO,
                title="Healthy projection",
                detail="No negative buckets and no past-due red flags detected.",
            )
        )
    return messages


def build_cash_flow_forecast_advisor() -> WizardAdvisor:
    advisor = WizardAdvisor(wizard_code="cash_flow_forecast")
    advisor.register("setup", _setup_rules)
    advisor.register("review", _review_rules)
    return advisor
