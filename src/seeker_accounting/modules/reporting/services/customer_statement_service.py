from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.reporting.dto.customer_statement_dto import (
    CustomerStatementLineDTO,
    CustomerStatementReportDTO,
)
from seeker_accounting.modules.reporting.dto.operational_report_filter_dto import (
    OperationalReportFilterDTO,
)
from seeker_accounting.modules.reporting.dto.print_preview_dto import (
    PrintPreviewMetaDTO,
    PrintPreviewRowDTO,
)
from seeker_accounting.modules.reporting.repositories.customer_statement_repository import (
    CustomerStatementRepository,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

CustomerStatementRepositoryFactory = Callable[[Session], CustomerStatementRepository]

_ZERO = Decimal("0.00")


class CustomerStatementService:
    """Builds customer statements from posted AR source truth."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        repository_factory: CustomerStatementRepositoryFactory,
        permission_service: PermissionService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._repository_factory = repository_factory
        self._permission_service = permission_service

    def get_statement(self, filter_dto: OperationalReportFilterDTO) -> CustomerStatementReportDTO:
        if self._permission_service is not None:
            self._permission_service.require_permission("reports.customer_statements.view")
        company_id, customer_id, date_from, date_to = self._normalize_filter(filter_dto)
        with self._unit_of_work_factory() as uow:
            repo = self._repository_factory(uow.session)
            identity = repo.get_customer_identity(company_id, customer_id)
            if identity is None:
                raise NotFoundError("Customer was not found for this company.")
            opening_balance = repo.sum_opening_balance(company_id, customer_id, date_from)
            movement_rows = repo.list_period_movements(company_id, customer_id, date_from, date_to)

        running_balance = opening_balance
        lines: list[CustomerStatementLineDTO] = []
        total_invoices = _ZERO
        total_receipts = _ZERO
        for row in movement_rows:
            running_balance += row.invoice_amount - row.receipt_amount
            total_invoices += row.invoice_amount
            total_receipts += row.receipt_amount
            lines.append(
                CustomerStatementLineDTO(
                    movement_date=row.movement_date,
                    movement_type_label="Invoice" if row.movement_kind == "invoice" else "Receipt",
                    document_number=row.document_number,
                    reference_text=row.reference_text,
                    description=row.description,
                    invoice_amount=row.invoice_amount,
                    receipt_amount=row.receipt_amount,
                    running_balance=running_balance.quantize(Decimal("0.01")),
                    journal_entry_id=row.journal_entry_id,
                    source_document_type=row.source_document_type,
                    source_document_id=row.source_document_id,
                )
            )

        closing_balance = (opening_balance + total_invoices - total_receipts).quantize(Decimal("0.01"))
        return CustomerStatementReportDTO(
            company_id=company_id,
            customer_id=customer_id,
            customer_code=identity[0],
            customer_name=identity[1],
            date_from=date_from,
            date_to=date_to,
            opening_balance=opening_balance.quantize(Decimal("0.01")),
            total_invoices=total_invoices.quantize(Decimal("0.01")),
            total_receipts=total_receipts.quantize(Decimal("0.01")),
            closing_balance=closing_balance,
            lines=tuple(lines),
            has_activity=bool(lines) or opening_balance != _ZERO,
        )

    def build_print_preview_meta(
        self,
        report_dto: CustomerStatementReportDTO,
        company_name: str,
    ) -> PrintPreviewMetaDTO:
        filter_summary = (
            f"Customer: {report_dto.customer_code} | "
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
                    amount_text=self._fmt(line.invoice_amount) if line.invoice_amount else "",
                    secondary_amount_text=self._fmt(line.receipt_amount) if line.receipt_amount else "",
                    tertiary_amount_text=self._fmt(line.running_balance),
                )
            )
        rows.append(
            PrintPreviewRowDTO(
                row_type="subtotal",
                reference_code=None,
                label="Closing Balance",
                amount_text=self._fmt(report_dto.total_invoices),
                secondary_amount_text=self._fmt(report_dto.total_receipts),
                tertiary_amount_text=self._fmt(report_dto.closing_balance),
            )
        )
        return PrintPreviewMetaDTO(
            report_title="Customer Statement",
            company_name=company_name,
            period_label=self._period_label(report_dto.date_from, report_dto.date_to),
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            filter_summary=filter_summary,
            amount_headers=("Invoices", "Receipts", "Balance"),
            rows=tuple(rows),
        )

    def _normalize_filter(
        self,
        filter_dto: OperationalReportFilterDTO,
    ) -> tuple[int, int, date | None, date | None]:
        company_id = filter_dto.company_id
        customer_id = filter_dto.customer_id
        if not isinstance(company_id, int) or company_id <= 0:
            raise ValidationError("Select an active company to run customer statements.")
        if not isinstance(customer_id, int) or customer_id <= 0:
            raise ValidationError("Select a customer to run the statement.")
        if not filter_dto.posted_only:
            raise ValidationError("Customer statements are limited to posted subledger truth.")
        date_from = filter_dto.date_from
        date_to = filter_dto.date_to or filter_dto.as_of_date
        if date_from and date_to and date_to < date_from:
            raise ValidationError("The 'To' date must be on or after the 'From' date.")
        return company_id, customer_id, date_from, date_to

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
