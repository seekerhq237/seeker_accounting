"""PayrollSummaryService — read-only payroll summary and exposure views.

No new truth tables.  Assembles summaries from:
  - payroll_runs and payroll_run_employees (calculation truth)
  - payroll_payment_records (employee net-pay settlement facts)
  - payroll_remittance_batches (statutory settlement facts)
"""

from __future__ import annotations

from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.payroll.dto.payroll_summary_dto import (
    PayrollNetPayExposureDTO,
    PayrollPeriodSummaryDTO,
    PayrollRunSummaryDTO,
    PayrollStatutoryExposureDTO,
)
from seeker_accounting.modules.payroll.repositories.payroll_run_repository import (
    PayrollRunRepository,
)
from seeker_accounting.modules.payroll.repositories.payroll_summary_repository import (
    PayrollSummaryRepository,
)
from seeker_accounting.platform.exceptions import NotFoundError

_AUTHORITY_LABELS = {
    "dgi": "DGI (Tax Authority)",
    "cnps": "CNPS (Social Insurance)",
    "other": "Other Authority",
}

_CALENDAR_MONTHS = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December",
}


class PayrollSummaryService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        run_repository_factory: Callable[[Session], PayrollRunRepository],
        summary_repository_factory: Callable[[Session], PayrollSummaryRepository],
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._run_repo_factory = run_repository_factory
        self._summary_repo_factory = summary_repository_factory

    def get_run_summary(
        self, company_id: int, run_id: int
    ) -> PayrollRunSummaryDTO:
        with self._uow_factory() as uow:
            run = self._run_repo_factory(uow.session).get_by_id(company_id, run_id)
            if run is None:
                raise NotFoundError("Payroll run not found.")
            summary_repo = self._summary_repo_factory(uow.session)
            totals = summary_repo.get_run_employee_totals(company_id, run_id)
            error_count = summary_repo.get_error_count(company_id, run_id)
            pay_counts = summary_repo.get_payment_status_counts(company_id, run_id)
            return PayrollRunSummaryDTO(
                run_id=run.id,
                run_reference=run.run_reference,
                run_label=run.run_label,
                period_year=run.period_year,
                period_month=run.period_month,
                status_code=run.status_code,
                currency_code=run.currency_code,
                total_gross_earnings=totals["gross_earnings"],
                total_net_payable=totals["net_payable"],
                total_taxes=totals["taxes"],
                total_employee_deductions=totals["deductions"],
                total_employer_contributions=totals["employer_contributions"],
                total_employer_cost=totals["employer_cost"],
                included_count=totals["included_count"],
                error_count=error_count,
                paid_count=pay_counts["paid"],
                partial_count=pay_counts["partial"],
                unpaid_count=pay_counts["unpaid"],
                is_posted=run.status_code == "posted",
                journal_entry_id=run.posted_journal_entry_id,
            )

    def get_period_summary(
        self, company_id: int, period_year: int, period_month: int
    ) -> PayrollPeriodSummaryDTO:
        with self._uow_factory() as uow:
            run = self._run_repo_factory(uow.session).get_by_period(
                company_id, period_year, period_month
            )
            summary_repo = self._summary_repo_factory(uow.session)

            run_summary: PayrollRunSummaryDTO | None = None
            net_pay_exposure = PayrollNetPayExposureDTO(
                total_net_payable=Decimal("0"),
                total_paid=Decimal("0"),
                outstanding=Decimal("0"),
                paid_count=0,
                partial_count=0,
                unpaid_count=0,
            )
            statutory: list[PayrollStatutoryExposureDTO] = []

            if run is not None:
                totals = summary_repo.get_run_employee_totals(company_id, run.id)
                error_count = summary_repo.get_error_count(company_id, run.id)
                pay_counts = summary_repo.get_payment_status_counts(company_id, run.id)
                run_summary = PayrollRunSummaryDTO(
                    run_id=run.id,
                    run_reference=run.run_reference,
                    run_label=run.run_label,
                    period_year=run.period_year,
                    period_month=run.period_month,
                    status_code=run.status_code,
                    currency_code=run.currency_code,
                    total_gross_earnings=totals["gross_earnings"],
                    total_net_payable=totals["net_payable"],
                    total_taxes=totals["taxes"],
                    total_employee_deductions=totals["deductions"],
                    total_employer_contributions=totals["employer_contributions"],
                    total_employer_cost=totals["employer_cost"],
                    included_count=totals["included_count"],
                    error_count=error_count,
                    paid_count=pay_counts["paid"],
                    partial_count=pay_counts["partial"],
                    unpaid_count=pay_counts["unpaid"],
                    is_posted=run.status_code == "posted",
                    journal_entry_id=run.posted_journal_entry_id,
                )
                exposure = summary_repo.get_net_pay_exposure(company_id, run.id)
                net_pay_exposure = PayrollNetPayExposureDTO(
                    total_net_payable=exposure["total_net"],
                    total_paid=exposure["total_paid"],
                    outstanding=exposure["outstanding"],
                    paid_count=pay_counts["paid"],
                    partial_count=pay_counts["partial"],
                    unpaid_count=pay_counts["unpaid"],
                )
                remittance_rows = summary_repo.get_remittance_exposure_by_authority(
                    company_id, run.id
                )
                statutory = [
                    PayrollStatutoryExposureDTO(
                        remittance_authority_code=row["authority"],
                        authority_label=_AUTHORITY_LABELS.get(row["authority"], row["authority"]),
                        total_due=row["total_due"],
                        total_remitted=row["total_paid"],
                        outstanding=row["total_due"] - row["total_paid"],
                        batch_count=row["batch_count"],
                    )
                    for row in remittance_rows
                ]

            return PayrollPeriodSummaryDTO(
                company_id=company_id,
                period_year=period_year,
                period_month=period_month,
                run_summary=run_summary,
                net_pay_exposure=net_pay_exposure,
                statutory_exposures=tuple(statutory),
            )
