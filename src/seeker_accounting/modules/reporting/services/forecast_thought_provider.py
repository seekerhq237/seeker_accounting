"""Forecasting-domain ambient thoughts (Phase 4).

Uses live AR/AP aging and cash flow projection data to surface
actionable forward-looking thoughts.  All three thoughts use
``source_kind="trend"`` and tone ``"projection"`` or ``"caution"``
to make clear they are estimates, not confirmed facts.

Codes produced:

``forecast.ar.overdue_high``
    Overdue AR (1+ days) exceeds 30 % of total outstanding AR on the
    current company.  Surfaces when the user is on a sales, customer,
    or reports page.

``forecast.ap.overdue_payable``
    Supplier balances exist that are past their due date (31+ days).
    Surfaces when the user is on a purchases, supplier, or reports page.

``forecast.cashflow.net_negative``
    The 8-week cash flow projection has at least one week with a
    negative projected closing balance.  Surfaces on treasury or reports
    pages.

All three provider calls are wrapped in broad exception handlers so a
slow or broken query never silences the rest of the ambient layer.

Performance note: these are lightweight aggregate queries.  If the
refresh rate becomes a concern a TTL cache can be added; deferred for
now because the 500 ms overlay debounce already limits call frequency.
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.modules.reporting.dto.operational_report_filter_dto import (
    OperationalReportFilterDTO,
)
from seeker_accounting.shared.dto.ambient_thought_dto import (
    AmbientThoughtContextDTO,
    AmbientThoughtDTO,
)

if TYPE_CHECKING:
    from seeker_accounting.app.dependency.service_registry import ServiceRegistry


logger = logging.getLogger(__name__)

_ZERO = Decimal("0.00")

# Overdue ratio at which the AR projection thought fires.
_OVERDUE_RATIO_THRESHOLD = Decimal("0.30")

_AR_NAV_IDS = {
    nav_ids.SALES_INVOICES,
    nav_ids.SALES_ORDERS,
    nav_ids.CUSTOMER_RECEIPTS,
    nav_ids.CUSTOMERS,
    nav_ids.CUSTOMER_DETAIL,
    nav_ids.REPORTS,
}

_AP_NAV_IDS = {
    nav_ids.PURCHASE_BILLS,
    nav_ids.PURCHASE_ORDERS,
    nav_ids.SUPPLIER_PAYMENTS,
    nav_ids.SUPPLIERS,
    nav_ids.SUPPLIER_DETAIL,
    nav_ids.REPORTS,
}

_CASH_NAV_IDS = {
    nav_ids.TREASURY_TRANSACTIONS,
    nav_ids.TREASURY_TRANSFERS,
    nav_ids.REPORTS,
}


class ForecastThoughtProvider:
    """Produces projection-class thoughts from live AR/AP/cash-flow data."""

    def __init__(self, service_registry: "ServiceRegistry") -> None:
        self._sr = service_registry

    def provide(
        self, context: AmbientThoughtContextDTO
    ) -> list[AmbientThoughtDTO]:
        if context.company_id is None:
            return []

        nav = context.nav_id or ""
        needs_ar = nav in _AR_NAV_IDS
        needs_ap = nav in _AP_NAV_IDS
        needs_cash = nav in _CASH_NAV_IDS

        if not (needs_ar or needs_ap or needs_cash):
            return []

        thoughts: list[AmbientThoughtDTO] = []
        as_of = date.today()
        filter_dto = OperationalReportFilterDTO(
            company_id=context.company_id,
            as_of_date=as_of,
        )

        if needs_ar:
            thoughts.extend(self._ar_thoughts(context, filter_dto))
        if needs_ap:
            thoughts.extend(self._ap_thoughts(context, filter_dto))
        if needs_cash:
            thoughts.extend(self._cash_thoughts(context, as_of))

        return thoughts

    # ── AR ────────────────────────────────────────────────────────────

    def _ar_thoughts(
        self,
        context: AmbientThoughtContextDTO,
        filter_dto: OperationalReportFilterDTO,
    ) -> list[AmbientThoughtDTO]:
        try:
            report = self._sr.ar_aging_report_service.get_report(filter_dto)
        except Exception:
            logger.debug(
                "ForecastThoughtProvider: AR aging lookup failed.", exc_info=True
            )
            return []

        if report.grand_total <= _ZERO:
            return []

        overdue = (
            report.total_bucket_1_30
            + report.total_bucket_31_60
            + report.total_bucket_61_90
            + report.total_bucket_91_plus
        )
        if overdue <= _ZERO:
            return []

        ratio = overdue / report.grand_total
        if ratio < _OVERDUE_RATIO_THRESHOLD:
            return []

        pct = int(ratio * 100)
        urgency = 0.6 if ratio >= Decimal("0.5") else 0.35

        return [
            AmbientThoughtDTO(
                thought_code="forecast.ar.overdue_high",
                tone="projection",
                summary=(
                    f"{pct}% of outstanding receivables are past their due date."
                ),
                detail=(
                    "A high overdue ratio can compress cash inflow and may indicate "
                    "collection risk. Review the AR aging report and follow up on "
                    "overdue accounts."
                ),
                confidence_label="Watch",
                relevance=0.75,
                urgency=urgency,
                confidence=0.9,
                importance=0.7,
                source_kind="trend",
                nav_id=context.nav_id,
                why_items=(
                    f"Total outstanding AR: {report.grand_total:,.2f}.",
                    f"Overdue (1+ days): {overdue:,.2f} ({pct}%).",
                    "Threshold: 30% overdue triggers this projection.",
                ),
            )
        ]

    # ── AP ────────────────────────────────────────────────────────────

    def _ap_thoughts(
        self,
        context: AmbientThoughtContextDTO,
        filter_dto: OperationalReportFilterDTO,
    ) -> list[AmbientThoughtDTO]:
        try:
            report = self._sr.ap_aging_report_service.get_report(filter_dto)
        except Exception:
            logger.debug(
                "ForecastThoughtProvider: AP aging lookup failed.", exc_info=True
            )
            return []

        if report.grand_total <= _ZERO:
            return []

        overdue = (
            report.total_bucket_31_60
            + report.total_bucket_61_90
            + report.total_bucket_91_plus
        )
        if overdue <= _ZERO:
            return []

        return [
            AmbientThoughtDTO(
                thought_code="forecast.ap.overdue_payable",
                tone="caution",
                summary="Some supplier balances are past their due date.",
                detail=(
                    "Overdue payables can strain supplier relationships and may "
                    "attract late payment penalties. Review the AP aging report "
                    "to prioritise payments."
                ),
                confidence_label="Likely",
                relevance=0.7,
                urgency=0.55,
                confidence=0.9,
                importance=0.65,
                source_kind="trend",
                nav_id=context.nav_id,
                why_items=(
                    f"Total outstanding AP: {report.grand_total:,.2f}.",
                    f"Overdue (31+ days): {overdue:,.2f}.",
                ),
            )
        ]

    # ── Cash flow ─────────────────────────────────────────────────────

    def _cash_thoughts(
        self,
        context: AmbientThoughtContextDTO,
        as_of: date,
    ) -> list[AmbientThoughtDTO]:
        try:
            from seeker_accounting.modules.reporting.dto.cash_flow_forecast_dto import (
                CashFlowBucketUnit,
            )

            forecast = self._sr.cash_flow_forecast_service.forecast(
                context.company_id,
                as_of,
                bucket_unit=CashFlowBucketUnit.WEEK,
                bucket_count=8,
            )
        except Exception:
            logger.debug(
                "ForecastThoughtProvider: cash flow forecast failed.", exc_info=True
            )
            return []

        if not forecast.has_negative_bucket:
            return []

        negative_buckets = [b for b in forecast.buckets if b.closing_balance < _ZERO]
        if not negative_buckets:
            return []

        first = negative_buckets[0]

        return [
            AmbientThoughtDTO(
                thought_code="forecast.cashflow.net_negative",
                tone="projection",
                summary=f"Cash is projected to go negative around {first.label}.",
                detail=(
                    "Based on open AR and AP due dates, the projected cash balance "
                    "turns negative within the next 8 weeks. This is a projection — "
                    "actual collections and payments may differ."
                ),
                confidence_label="Watch",
                relevance=0.85,
                urgency=0.8,
                confidence=0.65,
                importance=0.85,
                source_kind="trend",
                nav_id=context.nav_id,
                why_items=(
                    f"Opening cash balance: {forecast.opening_cash_balance:,.2f}.",
                    f"First projected negative week: {first.label}.",
                    f"Projected closing balance: {first.closing_balance:,.2f}.",
                ),
            )
        ]
