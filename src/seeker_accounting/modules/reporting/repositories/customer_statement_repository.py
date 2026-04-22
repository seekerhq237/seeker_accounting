from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.customers.models.customer import Customer
from seeker_accounting.modules.sales.models.customer_receipt import CustomerReceipt
from seeker_accounting.modules.sales.models.sales_invoice import SalesInvoice


@dataclass(frozen=True, slots=True)
class CustomerStatementMovementRow:
    movement_date: date
    movement_kind: str
    document_number: str
    reference_text: str | None
    description: str | None
    invoice_amount: Decimal
    receipt_amount: Decimal
    journal_entry_id: int | None
    source_document_type: str
    source_document_id: int


class CustomerStatementRepository:
    """Query-only repository for customer statement reporting."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_customer_identity(self, company_id: int, customer_id: int) -> tuple[str, str] | None:
        stmt = select(Customer.customer_code, Customer.display_name).where(
            Customer.company_id == company_id,
            Customer.id == customer_id,
        )
        row = self._session.execute(stmt).one_or_none()
        if row is None:
            return None
        return row.customer_code, row.display_name

    def sum_opening_balance(
        self,
        company_id: int,
        customer_id: int,
        date_from: date | None,
    ) -> Decimal:
        if date_from is None:
            return Decimal("0.00")

        invoice_stmt = select(func.coalesce(func.sum(SalesInvoice.total_amount), 0)).where(
            SalesInvoice.company_id == company_id,
            SalesInvoice.customer_id == customer_id,
            SalesInvoice.status_code == "posted",
            SalesInvoice.invoice_date < date_from,
        )
        receipt_stmt = select(func.coalesce(func.sum(CustomerReceipt.amount_received), 0)).where(
            CustomerReceipt.company_id == company_id,
            CustomerReceipt.customer_id == customer_id,
            CustomerReceipt.status_code == "posted",
            CustomerReceipt.receipt_date < date_from,
        )
        invoice_total = self._to_decimal(self._session.scalar(invoice_stmt))
        receipt_total = self._to_decimal(self._session.scalar(receipt_stmt))
        return (invoice_total - receipt_total).quantize(Decimal("0.01"))

    def list_period_movements(
        self,
        company_id: int,
        customer_id: int,
        date_from: date | None,
        date_to: date | None,
    ) -> list[CustomerStatementMovementRow]:
        rows = [
            *self._list_invoice_rows(company_id, customer_id, date_from, date_to),
            *self._list_receipt_rows(company_id, customer_id, date_from, date_to),
        ]
        rows.sort(
            key=lambda row: (
                row.movement_date,
                0 if row.movement_kind == "invoice" else 1,
                row.document_number,
            )
        )
        return rows

    def _list_invoice_rows(
        self,
        company_id: int,
        customer_id: int,
        date_from: date | None,
        date_to: date | None,
    ) -> list[CustomerStatementMovementRow]:
        stmt = select(
            SalesInvoice.id.label("document_id"),
            SalesInvoice.invoice_number.label("document_number"),
            SalesInvoice.invoice_date.label("movement_date"),
            SalesInvoice.reference_number.label("reference_text"),
            SalesInvoice.notes.label("description"),
            SalesInvoice.total_amount.label("invoice_amount"),
            SalesInvoice.posted_journal_entry_id.label("journal_entry_id"),
        ).where(
            SalesInvoice.company_id == company_id,
            SalesInvoice.customer_id == customer_id,
            SalesInvoice.status_code == "posted",
        )
        if date_from is not None:
            stmt = stmt.where(SalesInvoice.invoice_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(SalesInvoice.invoice_date <= date_to)
        stmt = stmt.order_by(SalesInvoice.invoice_date.asc(), SalesInvoice.invoice_number.asc(), SalesInvoice.id.asc())
        return [
            CustomerStatementMovementRow(
                movement_date=row.movement_date,
                movement_kind="invoice",
                document_number=row.document_number or f"Invoice #{row.document_id}",
                reference_text=row.reference_text,
                description=row.description,
                invoice_amount=self._to_decimal(row.invoice_amount),
                receipt_amount=Decimal("0.00"),
                journal_entry_id=row.journal_entry_id,
                source_document_type="sales_invoice",
                source_document_id=int(row.document_id),
            )
            for row in self._session.execute(stmt)
        ]

    def _list_receipt_rows(
        self,
        company_id: int,
        customer_id: int,
        date_from: date | None,
        date_to: date | None,
    ) -> list[CustomerStatementMovementRow]:
        stmt = select(
            CustomerReceipt.id.label("document_id"),
            CustomerReceipt.receipt_number.label("document_number"),
            CustomerReceipt.receipt_date.label("movement_date"),
            CustomerReceipt.reference_number.label("reference_text"),
            CustomerReceipt.notes.label("description"),
            CustomerReceipt.amount_received.label("receipt_amount"),
            CustomerReceipt.posted_journal_entry_id.label("journal_entry_id"),
        ).where(
            CustomerReceipt.company_id == company_id,
            CustomerReceipt.customer_id == customer_id,
            CustomerReceipt.status_code == "posted",
        )
        if date_from is not None:
            stmt = stmt.where(CustomerReceipt.receipt_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(CustomerReceipt.receipt_date <= date_to)
        stmt = stmt.order_by(
            CustomerReceipt.receipt_date.asc(),
            CustomerReceipt.receipt_number.asc(),
            CustomerReceipt.id.asc(),
        )
        return [
            CustomerStatementMovementRow(
                movement_date=row.movement_date,
                movement_kind="receipt",
                document_number=row.document_number or f"Receipt #{row.document_id}",
                reference_text=row.reference_text,
                description=row.description,
                invoice_amount=Decimal("0.00"),
                receipt_amount=self._to_decimal(row.receipt_amount),
                journal_entry_id=row.journal_entry_id,
                source_document_type="customer_receipt",
                source_document_id=int(row.document_id),
            )
            for row in self._session.execute(stmt)
        ]

    @staticmethod
    def _to_decimal(value: object) -> Decimal:
        if isinstance(value, Decimal):
            return value.quantize(Decimal("0.01"))
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))
