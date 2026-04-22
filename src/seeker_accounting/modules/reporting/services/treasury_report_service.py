from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.reporting.dto.operational_report_filter_dto import (
    OperationalReportFilterDTO,
)
from seeker_accounting.modules.reporting.dto.print_preview_dto import (
    PrintPreviewMetaDTO,
    PrintPreviewRowDTO,
)
from seeker_accounting.modules.reporting.dto.treasury_report_dto import (
    TreasuryAccountSummaryRowDTO,
    TreasuryMovementRowDTO,
    TreasuryReportDTO,
)
from seeker_accounting.modules.reporting.repositories.treasury_report_repository import (
    TreasuryReportRepository,
)
from seeker_accounting.platform.exceptions import ValidationError

TreasuryReportRepositoryFactory = Callable[[Session], TreasuryReportRepository]

_ZERO = Decimal("0.00")


class TreasuryReportService:
    """Builds treasury operational report views from posted treasury truth."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        repository_factory: TreasuryReportRepositoryFactory,
        permission_service: PermissionService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._repository_factory = repository_factory
        self._permission_service = permission_service

    def get_report(self, filter_dto: OperationalReportFilterDTO) -> TreasuryReportDTO:
        if self._permission_service is not None:
            self._permission_service.require_permission("reports.treasury_reports.view")
        company_id, date_from, date_to, financial_account_id = self._normalize_filter(filter_dto)
        opening_cutoff = date_from - timedelta(days=1) if date_from is not None else None
        with self._unit_of_work_factory() as uow:
            repo = self._repository_factory(uow.session)
            opening_rows = repo.list_movement_rows(company_id, None, opening_cutoff, financial_account_id)
            period_rows = repo.list_movement_rows(company_id, date_from, date_to, financial_account_id)

        account_state: dict[int, dict[str, object]] = {}
        for row in opening_rows:
            state = account_state.setdefault(
                row.financial_account_id,
                {
                    "account_code": row.account_code,
                    "account_name": row.account_name,
                    "account_type_code": row.account_type_code,
                    "opening": _ZERO,
                    "inflow": _ZERO,
                    "outflow": _ZERO,
                    "movement_count": 0,
                },
            )
            state["opening"] = self._to_decimal(state["opening"]) + row.signed_amount

        running_by_account = {
            account_id: self._to_decimal(values["opening"])
            for account_id, values in account_state.items()
        }
        movement_rows: list[TreasuryMovementRowDTO] = []
        for row in period_rows:
            state = account_state.setdefault(
                row.financial_account_id,
                {
                    "account_code": row.account_code,
                    "account_name": row.account_name,
                    "account_type_code": row.account_type_code,
                    "opening": _ZERO,
                    "inflow": _ZERO,
                    "outflow": _ZERO,
                    "movement_count": 0,
                },
            )
            amount = row.signed_amount
            if amount >= _ZERO:
                state["inflow"] = self._to_decimal(state["inflow"]) + amount
            else:
                state["outflow"] = self._to_decimal(state["outflow"]) + abs(amount)
            state["movement_count"] = int(state["movement_count"]) + 1
            current_running = running_by_account.get(row.financial_account_id, self._to_decimal(state["opening"]))
            current_running += amount
            running_by_account[row.financial_account_id] = current_running.quantize(Decimal("0.01"))
            movement_rows.append(
                TreasuryMovementRowDTO(
                    financial_account_id=row.financial_account_id,
                    account_code=row.account_code,
                    account_name=row.account_name,
                    account_type_code=row.account_type_code,
                    transaction_date=row.transaction_date,
                    document_number=row.document_number,
                    movement_type_label=row.movement_type_label,
                    reference_text=row.reference_text,
                    description=row.description,
                    inflow_amount=amount if amount >= _ZERO else _ZERO,
                    outflow_amount=abs(amount) if amount < _ZERO else _ZERO,
                    running_balance=running_by_account[row.financial_account_id],
                    journal_entry_id=row.journal_entry_id,
                    source_document_type=row.source_document_type,
                    source_document_id=row.source_document_id,
                )
            )

        account_rows = tuple(
            sorted(
                (
                    TreasuryAccountSummaryRowDTO(
                        financial_account_id=account_id,
                        account_code=str(values["account_code"]),
                        account_name=str(values["account_name"]),
                        account_type_code=str(values["account_type_code"]),
                        opening_balance=self._to_decimal(values["opening"]),
                        inflow_amount=self._to_decimal(values["inflow"]),
                        outflow_amount=self._to_decimal(values["outflow"]),
                        closing_balance=(
                            self._to_decimal(values["opening"])
                            + self._to_decimal(values["inflow"])
                            - self._to_decimal(values["outflow"])
                        ).quantize(Decimal("0.01")),
                        movement_count=int(values["movement_count"]),
                    )
                    for account_id, values in account_state.items()
                ),
                key=lambda row: (row.account_name.lower(), row.account_code, row.financial_account_id),
            )
        )

        return TreasuryReportDTO(
            company_id=company_id,
            date_from=date_from,
            date_to=date_to,
            selected_financial_account_id=financial_account_id,
            account_rows=account_rows,
            movement_rows=tuple(movement_rows),
            total_opening=sum((row.opening_balance for row in account_rows), _ZERO).quantize(Decimal("0.01")),
            total_inflow=sum((row.inflow_amount for row in account_rows), _ZERO).quantize(Decimal("0.01")),
            total_outflow=sum((row.outflow_amount for row in account_rows), _ZERO).quantize(Decimal("0.01")),
            total_closing=sum((row.closing_balance for row in account_rows), _ZERO).quantize(Decimal("0.01")),
            has_activity=bool(account_rows),
        )

    def build_print_preview_meta(
        self,
        report_dto: TreasuryReportDTO,
        company_name: str,
    ) -> PrintPreviewMetaDTO:
        if report_dto.selected_financial_account_id is not None and report_dto.movement_rows:
            rows = tuple(
                PrintPreviewRowDTO(
                    row_type="line",
                    reference_code=row.document_number,
                    label=f"{row.transaction_date.strftime('%Y-%m-%d')} | {row.movement_type_label}",
                    amount_text=self._fmt(row.inflow_amount) if row.inflow_amount else "",
                    secondary_amount_text=self._fmt(row.outflow_amount) if row.outflow_amount else "",
                    tertiary_amount_text=self._fmt(row.running_balance),
                )
                for row in report_dto.movement_rows
            )
        else:
            rows = tuple(
                PrintPreviewRowDTO(
                    row_type="line",
                    reference_code=row.account_code,
                    label=row.account_name,
                    amount_text=self._fmt(row.inflow_amount),
                    secondary_amount_text=self._fmt(row.outflow_amount),
                    tertiary_amount_text=self._fmt(row.closing_balance),
                )
                for row in report_dto.account_rows
            )
        return PrintPreviewMetaDTO(
            report_title="Cash / Bank Report",
            company_name=company_name,
            period_label=self._period_label(report_dto.date_from, report_dto.date_to),
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            filter_summary=(
                f"Opening: {self._fmt(report_dto.total_opening)} | Inflow: {self._fmt(report_dto.total_inflow)} "
                f"| Closing: {self._fmt(report_dto.total_closing)}"
            ),
            amount_headers=("Inflow", "Outflow", "Closing"),
            rows=rows,
        )

    def _normalize_filter(
        self,
        filter_dto: OperationalReportFilterDTO,
    ) -> tuple[int, date | None, date | None, int | None]:
        company_id = filter_dto.company_id
        if not isinstance(company_id, int) or company_id <= 0:
            raise ValidationError("Select an active company to run cash and bank reports.")
        if not filter_dto.posted_only:
            raise ValidationError("Cash and bank reports are limited to posted treasury truth.")
        date_from = filter_dto.date_from
        date_to = filter_dto.date_to or filter_dto.as_of_date
        if date_from and date_to and date_to < date_from:
            raise ValidationError("The 'To' date must be on or after the 'From' date.")
        financial_account_id = (
            filter_dto.financial_account_id
            if isinstance(filter_dto.financial_account_id, int) and filter_dto.financial_account_id > 0
            else None
        )
        return company_id, date_from, date_to, financial_account_id

    @staticmethod
    def _period_label(date_from: date | None, date_to: date | None) -> str:
        if date_from and date_to:
            return f"{date_from.strftime('%d %b %Y')} - {date_to.strftime('%d %b %Y')}"
        if date_to:
            return f"Up to {date_to.strftime('%d %b %Y')}"
        if date_from:
            return f"From {date_from.strftime('%d %b %Y')}"
        return "All posted treasury activity"

    @staticmethod
    def _to_decimal(value: object) -> Decimal:
        if isinstance(value, Decimal):
            return value.quantize(Decimal("0.01"))
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))

    @staticmethod
    def _fmt(amount: Decimal) -> str:
        if amount == _ZERO:
            return "0.00"
        return f"{amount:,.2f}"
