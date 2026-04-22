from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.reporting.dto.operational_report_filter_dto import (
    OperationalReportFilterDTO,
)
from seeker_accounting.modules.reporting.dto.payroll_summary_report_dto import (
    PayrollSummaryEmployeeRowDTO,
    PayrollSummaryReportDTO,
    PayrollSummaryRunRowDTO,
    PayrollSummaryStatutoryRowDTO,
)
from seeker_accounting.modules.reporting.dto.print_preview_dto import (
    PrintPreviewMetaDTO,
    PrintPreviewRowDTO,
)
from seeker_accounting.modules.reporting.repositories.payroll_summary_report_repository import (
    PayrollSummaryReportRepository,
)
from seeker_accounting.platform.exceptions import ValidationError

PayrollSummaryReportRepositoryFactory = Callable[[Session], PayrollSummaryReportRepository]

_ZERO = Decimal("0.00")
_AUTHORITY_LABELS = {
    "cnps": "CNPS",
    "dgi": "DGI",
    "other": "Other",
}


class PayrollSummaryReportService:
    """Builds operational payroll summaries from posted payroll truth."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        repository_factory: PayrollSummaryReportRepositoryFactory,
        permission_service: PermissionService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._repository_factory = repository_factory
        self._permission_service = permission_service

    def get_report(self, filter_dto: OperationalReportFilterDTO) -> PayrollSummaryReportDTO:
        if self._permission_service is not None:
            self._permission_service.require_permission("reports.payroll_summary.view")
        company_id, date_from, date_to, run_id = self._normalize_filter(filter_dto)
        with self._unit_of_work_factory() as uow:
            repo = self._repository_factory(uow.session)
            run_rows = repo.list_run_rows(company_id, date_from, date_to, run_id=run_id)
            run_ids = tuple(row.run_id for row in run_rows)
            employee_rows = repo.list_employee_rows(company_id, run_ids)
            statutory_rows = repo.list_statutory_rows(company_id, run_ids)

        dto_run_rows = tuple(
            PayrollSummaryRunRowDTO(
                run_id=row.run_id,
                run_reference=row.run_reference,
                run_label=row.run_label,
                period_year=row.period_year,
                period_month=row.period_month,
                run_date=row.run_date,
                payment_date=row.payment_date,
                status_code=row.status_code,
                employee_count=row.employee_count,
                gross_pay=row.gross_pay,
                deductions=row.deductions,
                employer_cost=row.employer_cost,
                net_pay=row.net_pay,
                total_paid=row.total_paid,
                outstanding_net_pay=row.outstanding_net_pay,
                journal_entry_id=row.journal_entry_id,
            )
            for row in run_rows
        )
        dto_employee_rows = tuple(
            PayrollSummaryEmployeeRowDTO(
                employee_id=row.employee_id,
                employee_number=row.employee_number,
                employee_name=row.employee_name,
                run_id=row.run_id,
                run_employee_id=row.run_employee_id,
                gross_pay=row.gross_pay,
                deductions=row.deductions,
                employer_cost=row.employer_cost,
                net_pay=row.net_pay,
            )
            for row in employee_rows
        )
        dto_statutory_rows = tuple(
            PayrollSummaryStatutoryRowDTO(
                authority_code=row.authority_code,
                authority_label=_AUTHORITY_LABELS.get(row.authority_code, row.authority_code.upper()),
                total_due=row.total_due,
                total_remitted=row.total_remitted,
                outstanding=(row.total_due - row.total_remitted).quantize(Decimal("0.01")),
                batch_count=row.batch_count,
            )
            for row in statutory_rows
        )

        return PayrollSummaryReportDTO(
            company_id=company_id,
            date_from=date_from,
            date_to=date_to,
            selected_run_id=run_id,
            run_rows=dto_run_rows,
            employee_rows=dto_employee_rows,
            statutory_rows=dto_statutory_rows,
            total_gross_pay=sum((row.gross_pay for row in dto_run_rows), _ZERO).quantize(Decimal("0.01")),
            total_deductions=sum((row.deductions for row in dto_run_rows), _ZERO).quantize(Decimal("0.01")),
            total_employer_cost=sum((row.employer_cost for row in dto_run_rows), _ZERO).quantize(Decimal("0.01")),
            total_net_pay=sum((row.net_pay for row in dto_run_rows), _ZERO).quantize(Decimal("0.01")),
            total_paid=sum((row.total_paid for row in dto_run_rows), _ZERO).quantize(Decimal("0.01")),
            total_outstanding=sum((row.outstanding_net_pay for row in dto_run_rows), _ZERO).quantize(Decimal("0.01")),
            has_data=bool(dto_run_rows),
        )

    def build_print_preview_meta(
        self,
        report_dto: PayrollSummaryReportDTO,
        company_name: str,
    ) -> PrintPreviewMetaDTO:
        rows = tuple(
            PrintPreviewRowDTO(
                row_type="line",
                reference_code=row.run_reference,
                label=f"{row.period_month:02d}/{row.period_year} | {row.run_label}",
                amount_text=self._fmt(row.gross_pay),
                secondary_amount_text=self._fmt(row.deductions),
                tertiary_amount_text=self._fmt(row.net_pay),
            )
            for row in report_dto.run_rows
        )
        return PrintPreviewMetaDTO(
            report_title="Payroll Summary",
            company_name=company_name,
            period_label=self._period_label(report_dto.date_from, report_dto.date_to, report_dto.selected_run_id),
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            filter_summary=(
                f"Runs: {len(report_dto.run_rows)} | Employer Cost: {self._fmt(report_dto.total_employer_cost)} "
                f"| Outstanding Net Pay: {self._fmt(report_dto.total_outstanding)}"
            ),
            amount_headers=("Gross", "Deductions", "Net"),
            rows=rows,
        )

    def _normalize_filter(
        self,
        filter_dto: OperationalReportFilterDTO,
    ) -> tuple[int, date | None, date | None, int | None]:
        company_id = filter_dto.company_id
        if not isinstance(company_id, int) or company_id <= 0:
            raise ValidationError("Select an active company to run payroll summaries.")
        if not filter_dto.posted_only:
            raise ValidationError("Payroll summary reporting is limited to posted payroll runs.")
        date_from = filter_dto.date_from
        date_to = filter_dto.date_to or filter_dto.as_of_date
        if date_from and date_to and date_to < date_from:
            raise ValidationError("The 'To' date must be on or after the 'From' date.")
        run_id = filter_dto.payroll_run_id if isinstance(filter_dto.payroll_run_id, int) and filter_dto.payroll_run_id > 0 else None
        return company_id, date_from, date_to, run_id

    @staticmethod
    def _period_label(date_from: date | None, date_to: date | None, selected_run_id: int | None) -> str:
        if selected_run_id is not None:
            return f"Selected payroll run #{selected_run_id}"
        if date_from and date_to:
            return f"{date_from.strftime('%d %b %Y')} - {date_to.strftime('%d %b %Y')}"
        if date_to:
            return f"Up to {date_to.strftime('%d %b %Y')}"
        if date_from:
            return f"From {date_from.strftime('%d %b %Y')}"
        return "All posted payroll runs"

    @staticmethod
    def _fmt(amount: Decimal) -> str:
        if amount == _ZERO:
            return "0.00"
        return f"{amount:,.2f}"
