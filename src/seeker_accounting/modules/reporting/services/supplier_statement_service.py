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
from seeker_accounting.modules.reporting.dto.print_preview_dto import (
    PrintPreviewMetaDTO,
    PrintPreviewRowDTO,
)
from seeker_accounting.modules.reporting.dto.supplier_statement_dto import (
    SupplierStatementLineDTO,
    SupplierStatementReportDTO,
)
from seeker_accounting.modules.reporting.repositories.supplier_statement_repository import (
    SupplierStatementRepository,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

SupplierStatementRepositoryFactory = Callable[[Session], SupplierStatementRepository]

_ZERO = Decimal("0.00")


class SupplierStatementService:
    """Builds supplier statements from posted AP source truth."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        repository_factory: SupplierStatementRepositoryFactory,
        permission_service: PermissionService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._repository_factory = repository_factory
        self._permission_service = permission_service

    def get_statement(self, filter_dto: OperationalReportFilterDTO) -> SupplierStatementReportDTO:
        if self._permission_service is not None:
            self._permission_service.require_permission("reports.supplier_statements.view")
        company_id, supplier_id, date_from, date_to = self._normalize_filter(filter_dto)
        with self._unit_of_work_factory() as uow:
            repo = self._repository_factory(uow.session)
            identity = repo.get_supplier_identity(company_id, supplier_id)
            if identity is None:
                raise NotFoundError("Supplier was not found for this company.")
            opening_balance = repo.sum_opening_balance(company_id, supplier_id, date_from)
            movement_rows = repo.list_period_movements(company_id, supplier_id, date_from, date_to)

        running_balance = opening_balance
        lines: list[SupplierStatementLineDTO] = []
        total_bills = _ZERO
        total_payments = _ZERO
        for row in movement_rows:
            running_balance += row.bill_amount - row.payment_amount
            total_bills += row.bill_amount
            total_payments += row.payment_amount
            lines.append(
                SupplierStatementLineDTO(
                    movement_date=row.movement_date,
                    movement_type_label="Bill" if row.movement_kind == "bill" else "Payment",
                    document_number=row.document_number,
                    reference_text=row.reference_text,
                    description=row.description,
                    bill_amount=row.bill_amount,
                    payment_amount=row.payment_amount,
                    running_balance=running_balance.quantize(Decimal("0.01")),
                    journal_entry_id=row.journal_entry_id,
                    source_document_type=row.source_document_type,
                    source_document_id=row.source_document_id,
                )
            )

        closing_balance = (opening_balance + total_bills - total_payments).quantize(Decimal("0.01"))
        return SupplierStatementReportDTO(
            company_id=company_id,
            supplier_id=supplier_id,
            supplier_code=identity[0],
            supplier_name=identity[1],
            date_from=date_from,
            date_to=date_to,
            opening_balance=opening_balance.quantize(Decimal("0.01")),
            total_bills=total_bills.quantize(Decimal("0.01")),
            total_payments=total_payments.quantize(Decimal("0.01")),
            closing_balance=closing_balance,
            lines=tuple(lines),
            has_activity=bool(lines) or opening_balance != _ZERO,
        )

    def build_print_preview_meta(
        self,
        report_dto: SupplierStatementReportDTO,
        company_name: str,
    ) -> PrintPreviewMetaDTO:
        filter_summary = (
            f"Supplier: {report_dto.supplier_code} | "
            f"Closing: {self._fmt(report_dto.closing_balance)}"
        )
        rows = [
            PrintPreviewRowDTO(
                row_type="subtotal",
                reference_code=None,
                label="Opening Balance",
                amount_text="",
                secondary_amount_text="",
                tertiary_amount_text=self._fmt(report_dto.opening_balance),
            )
        ]
        for line in report_dto.lines:
            rows.append(
                PrintPreviewRowDTO(
                    row_type="line",
                    reference_code=line.document_number,
                    label=f"{line.movement_date.strftime('%Y-%m-%d')} | {line.movement_type_label}",
                    amount_text=self._fmt(line.bill_amount) if line.bill_amount else "",
                    secondary_amount_text=self._fmt(line.payment_amount) if line.payment_amount else "",
                    tertiary_amount_text=self._fmt(line.running_balance),
                )
            )
        rows.append(
            PrintPreviewRowDTO(
                row_type="subtotal",
                reference_code=None,
                label="Closing Balance",
                amount_text=self._fmt(report_dto.total_bills),
                secondary_amount_text=self._fmt(report_dto.total_payments),
                tertiary_amount_text=self._fmt(report_dto.closing_balance),
            )
        )
        return PrintPreviewMetaDTO(
            report_title="Supplier Statement",
            company_name=company_name,
            period_label=self._period_label(report_dto.date_from, report_dto.date_to),
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            filter_summary=filter_summary,
            amount_headers=("Bills", "Payments", "Balance"),
            rows=tuple(rows),
        )

    def _normalize_filter(
        self,
        filter_dto: OperationalReportFilterDTO,
    ) -> tuple[int, int, date | None, date | None]:
        company_id = filter_dto.company_id
        supplier_id = filter_dto.supplier_id
        if not isinstance(company_id, int) or company_id <= 0:
            raise ValidationError("Select an active company to run supplier statements.")
        if not isinstance(supplier_id, int) or supplier_id <= 0:
            raise ValidationError("Select a supplier to run the statement.")
        if not filter_dto.posted_only:
            raise ValidationError("Supplier statements are limited to posted subledger truth.")
        date_from = filter_dto.date_from
        date_to = filter_dto.date_to or filter_dto.as_of_date
        if date_from and date_to and date_to < date_from:
            raise ValidationError("The 'To' date must be on or after the 'From' date.")
        return company_id, supplier_id, date_from, date_to

    @staticmethod
    def _period_label(date_from: date | None, date_to: date | None) -> str:
        if date_from and date_to:
            return f"{date_from.strftime('%d %b %Y')} - {date_to.strftime('%d %b %Y')}"
        if date_to:
            return f"Up to {date_to.strftime('%d %b %Y')}"
        if date_from:
            return f"From {date_from.strftime('%d %b %Y')}"
        return "All posted activity"

    @staticmethod
    def _fmt(amount: Decimal) -> str:
        if amount == _ZERO:
            return "0.00"
        return f"{amount:,.2f}"
