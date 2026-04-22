from __future__ import annotations

from seeker_accounting.app.context.active_company_context import ActiveCompanyContext
from seeker_accounting.modules.accounting.fiscal_periods.services.fiscal_calendar_service import (
    FiscalCalendarService,
)
from seeker_accounting.modules.reporting.dto.reporting_context_dto import ReportingContextDTO

_REPORT_BASIS = "Posted Only"


class ReportingContextService:
    """
    Assembles a ReportingContextDTO from the active company context
    and fiscal calendar service. No direct database access.
    """

    def __init__(
        self,
        fiscal_calendar_service: FiscalCalendarService,
        active_company_context: ActiveCompanyContext,
    ) -> None:
        self._fiscal_calendar_service = fiscal_calendar_service
        self._active_company_context = active_company_context

    def get_context(self, company_id: int | None = None) -> ReportingContextDTO:
        resolved_id = (
            company_id
            if isinstance(company_id, int)
            else self._active_company_context.company_id
        )

        if not isinstance(resolved_id, int) or resolved_id <= 0:
            return ReportingContextDTO(
                company_id=None,
                company_name="No active company",
                base_currency_code=None,
                fiscal_period_code=None,
                fiscal_period_status=None,
                fiscal_period_label=None,
                report_basis=_REPORT_BASIS,
            )

        company_name = self._active_company_context.company_name or "Unknown"
        currency_code = self._active_company_context.base_currency_code
        period_code: str | None = None
        period_status: str | None = None
        period_label: str | None = None

        try:
            period = self._fiscal_calendar_service.get_current_period(resolved_id)
            if period is not None:
                period_code = period.period_code
                period_status = period.status_code
                if period.start_date:
                    period_label = period.start_date.strftime("%b %Y")
                else:
                    period_label = period_code
        except Exception:
            pass

        return ReportingContextDTO(
            company_id=resolved_id,
            company_name=company_name,
            base_currency_code=currency_code,
            fiscal_period_code=period_code,
            fiscal_period_status=period_status,
            fiscal_period_label=period_label,
            report_basis=_REPORT_BASIS,
        )
