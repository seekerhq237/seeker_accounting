from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.reporting.dto.reporting_filter_dto import ReportingFilterDTO
from seeker_accounting.modules.reporting.dto.trial_balance_report_dto import (
    TrialBalanceReportDTO,
    TrialBalanceRowDTO,
)
from seeker_accounting.modules.reporting.repositories.trial_balance_report_repository import (
    TrialBalanceReportRepository,
)
from seeker_accounting.platform.exceptions import ValidationError

TrialBalanceReportRepositoryFactory = Callable[[Session], TrialBalanceReportRepository]

_ZERO = Decimal("0.00")


class TrialBalanceReportService:
    """Assembles a trial balance from posted journal entry lines."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        trial_balance_repository_factory: TrialBalanceReportRepositoryFactory,
        permission_service: PermissionService,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._trial_balance_repository_factory = trial_balance_repository_factory
        self._permission_service = permission_service

    def get_trial_balance(self, filter_dto: ReportingFilterDTO) -> TrialBalanceReportDTO:
        self._permission_service.require_permission("reports.trial_balance.view")
        company_id = filter_dto.company_id
        if not isinstance(company_id, int) or company_id <= 0:
            raise ValidationError("Select an active company to run the trial balance.")
        if not filter_dto.posted_only:
            raise ValidationError("Trial Balance is limited to posted journals.")

        date_from = filter_dto.date_from
        date_to = filter_dto.date_to
        self._validate_dates(date_from, date_to)

        with self._unit_of_work_factory() as uow:
            repo = self._trial_balance_repository_factory(uow.session)
            raw_rows = repo.list_account_activity(company_id, date_from, date_to)

        dto_rows: list[TrialBalanceRowDTO] = []
        totals = {
            "opening_debit": _ZERO,
            "opening_credit": _ZERO,
            "period_debit": _ZERO,
            "period_credit": _ZERO,
            "closing_debit": _ZERO,
            "closing_credit": _ZERO,
        }

        for row in raw_rows:
            closing_net = (row.opening_debit - row.opening_credit) + (row.period_debit - row.period_credit)
            closing_debit, closing_credit = self._split_balance(closing_net)

            dto_rows.append(
                TrialBalanceRowDTO(
                    account_id=row.account_id,
                    account_code=row.account_code,
                    account_name=row.account_name,
                    opening_debit=row.opening_debit,
                    opening_credit=row.opening_credit,
                    period_debit=row.period_debit,
                    period_credit=row.period_credit,
                    closing_debit=closing_debit,
                    closing_credit=closing_credit,
                )
            )

            totals["opening_debit"] += row.opening_debit
            totals["opening_credit"] += row.opening_credit
            totals["period_debit"] += row.period_debit
            totals["period_credit"] += row.period_credit
            totals["closing_debit"] += closing_debit
            totals["closing_credit"] += closing_credit

        return TrialBalanceReportDTO(
            company_id=company_id,
            date_from=date_from,
            date_to=date_to,
            rows=tuple(dto_rows),
            total_opening_debit=totals["opening_debit"],
            total_opening_credit=totals["opening_credit"],
            total_period_debit=totals["period_debit"],
            total_period_credit=totals["period_credit"],
            total_closing_debit=totals["closing_debit"],
            total_closing_credit=totals["closing_credit"],
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_dates(date_from: date | None, date_to: date | None) -> None:
        if date_from and date_to and date_to < date_from:
            raise ValidationError("The 'To' date must be on or after the 'From' date.")

    @staticmethod
    def _split_balance(net_amount: Decimal) -> tuple[Decimal, Decimal]:
        """Return (debit, credit) representation from a signed net amount."""
        if net_amount >= _ZERO:
            return net_amount, _ZERO
        return _ZERO, abs(net_amount)
