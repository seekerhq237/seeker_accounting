from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.accounting.journals.models.journal_entry import JournalEntry
from seeker_accounting.modules.accounting.journals.models.journal_entry_line import JournalEntryLine
from seeker_accounting.modules.accounting.reference_data.models.account_role_mapping import (
    AccountRoleMapping,
)
from seeker_accounting.modules.customers.models.customer import Customer
from seeker_accounting.modules.sales.models.customer_receipt import CustomerReceipt
from seeker_accounting.modules.sales.models.customer_receipt_allocation import (
    CustomerReceiptAllocation,
)
from seeker_accounting.modules.sales.models.sales_invoice import SalesInvoice


@dataclass(frozen=True, slots=True)
class ARAgingDocumentRow:
    customer_id: int
    customer_code: str
    customer_name: str
    document_kind: str
    document_number: str
    document_date: date
    due_date: date | None
    reference_text: str | None
    description: str | None
    open_amount: Decimal
    journal_entry_id: int | None
    source_document_type: str
    source_document_id: int


class ARAgingReportRepository:
    """Query-only repository for AR aging and supporting customer detail."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_open_documents(self, company_id: int, as_of_date: date) -> list[ARAgingDocumentRow]:
        rows = [
            *self._list_open_invoice_rows(company_id, as_of_date),
            *self._list_unapplied_receipt_rows(company_id, as_of_date),
        ]
        rows.sort(key=lambda row: (row.customer_name.lower(), row.customer_code, row.document_date, row.document_number))
        return rows

    def get_customer_identity(self, company_id: int, customer_id: int) -> tuple[str, str] | None:
        stmt = select(Customer.customer_code, Customer.display_name).where(
            Customer.company_id == company_id,
            Customer.id == customer_id,
        )
        row = self._session.execute(stmt).one_or_none()
        if row is None:
            return None
        return row.customer_code, row.display_name

    def sum_control_balance(self, company_id: int, as_of_date: date) -> Decimal | None:
        mapping_stmt = select(AccountRoleMapping.account_id).where(
            AccountRoleMapping.company_id == company_id,
            AccountRoleMapping.role_code == "ar_control",
        )
        account_id = self._session.scalar(mapping_stmt)
        if not isinstance(account_id, int):
            return None

        stmt = (
            select(
                func.coalesce(func.sum(JournalEntryLine.debit_amount), 0).label("debit"),
                func.coalesce(func.sum(JournalEntryLine.credit_amount), 0).label("credit"),
            )
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
            .where(
                JournalEntry.company_id == company_id,
                JournalEntry.status_code == "POSTED",
                JournalEntry.posted_at.is_not(None),
                JournalEntry.entry_date <= as_of_date,
                JournalEntryLine.account_id == account_id,
            )
        )
        row = self._session.execute(stmt).one()
        return (self._to_decimal(row.debit) - self._to_decimal(row.credit)).quantize(Decimal("0.01"))

    def _list_open_invoice_rows(self, company_id: int, as_of_date: date) -> list[ARAgingDocumentRow]:
        allocation_subquery = (
            select(
                CustomerReceiptAllocation.sales_invoice_id.label("invoice_id"),
                func.coalesce(func.sum(CustomerReceiptAllocation.allocated_amount), 0).label("allocated_amount"),
            )
            .join(CustomerReceipt, CustomerReceipt.id == CustomerReceiptAllocation.customer_receipt_id)
            .where(
                CustomerReceiptAllocation.company_id == company_id,
                CustomerReceipt.status_code == "posted",
                CustomerReceiptAllocation.allocation_date <= as_of_date,
            )
            .group_by(CustomerReceiptAllocation.sales_invoice_id)
            .subquery()
        )
        stmt = (
            select(
                SalesInvoice.id.label("document_id"),
                SalesInvoice.invoice_number.label("document_number"),
                SalesInvoice.invoice_date.label("document_date"),
                SalesInvoice.due_date.label("due_date"),
                SalesInvoice.reference_number.label("reference_text"),
                SalesInvoice.notes.label("description"),
                SalesInvoice.total_amount.label("gross_amount"),
                func.coalesce(allocation_subquery.c.allocated_amount, 0).label("allocated_amount"),
                SalesInvoice.posted_journal_entry_id.label("journal_entry_id"),
                Customer.id.label("customer_id"),
                Customer.customer_code.label("customer_code"),
                Customer.display_name.label("customer_name"),
            )
            .join(Customer, Customer.id == SalesInvoice.customer_id)
            .outerjoin(allocation_subquery, allocation_subquery.c.invoice_id == SalesInvoice.id)
            .where(
                SalesInvoice.company_id == company_id,
                SalesInvoice.status_code == "posted",
                SalesInvoice.invoice_date <= as_of_date,
            )
        )
        rows: list[ARAgingDocumentRow] = []
        for row in self._session.execute(stmt):
            open_amount = self._to_decimal(row.gross_amount) - self._to_decimal(row.allocated_amount)
            if open_amount <= Decimal("0.00"):
                continue
            rows.append(
                ARAgingDocumentRow(
                    customer_id=int(row.customer_id),
                    customer_code=row.customer_code or "",
                    customer_name=row.customer_name or "",
                    document_kind="invoice",
                    document_number=row.document_number or f"Invoice #{row.document_id}",
                    document_date=row.document_date,
                    due_date=row.due_date,
                    reference_text=row.reference_text,
                    description=row.description,
                    open_amount=open_amount.quantize(Decimal("0.01")),
                    journal_entry_id=row.journal_entry_id,
                    source_document_type="sales_invoice",
                    source_document_id=int(row.document_id),
                )
            )
        return rows

    def _list_unapplied_receipt_rows(self, company_id: int, as_of_date: date) -> list[ARAgingDocumentRow]:
        allocation_subquery = (
            select(
                CustomerReceiptAllocation.customer_receipt_id.label("receipt_id"),
                func.coalesce(func.sum(CustomerReceiptAllocation.allocated_amount), 0).label("allocated_amount"),
            )
            .where(
                CustomerReceiptAllocation.company_id == company_id,
                CustomerReceiptAllocation.allocation_date <= as_of_date,
            )
            .group_by(CustomerReceiptAllocation.customer_receipt_id)
            .subquery()
        )
        stmt = (
            select(
                CustomerReceipt.id.label("document_id"),
                CustomerReceipt.receipt_number.label("document_number"),
                CustomerReceipt.receipt_date.label("document_date"),
                CustomerReceipt.reference_number.label("reference_text"),
                CustomerReceipt.notes.label("description"),
                CustomerReceipt.amount_received.label("gross_amount"),
                func.coalesce(allocation_subquery.c.allocated_amount, 0).label("allocated_amount"),
                CustomerReceipt.posted_journal_entry_id.label("journal_entry_id"),
                Customer.id.label("customer_id"),
                Customer.customer_code.label("customer_code"),
                Customer.display_name.label("customer_name"),
            )
            .join(Customer, Customer.id == CustomerReceipt.customer_id)
            .outerjoin(allocation_subquery, allocation_subquery.c.receipt_id == CustomerReceipt.id)
            .where(
                CustomerReceipt.company_id == company_id,
                CustomerReceipt.status_code == "posted",
                CustomerReceipt.receipt_date <= as_of_date,
            )
        )
        rows: list[ARAgingDocumentRow] = []
        for row in self._session.execute(stmt):
            unapplied_amount = self._to_decimal(row.gross_amount) - self._to_decimal(row.allocated_amount)
            if unapplied_amount <= Decimal("0.00"):
                continue
            rows.append(
                ARAgingDocumentRow(
                    customer_id=int(row.customer_id),
                    customer_code=row.customer_code or "",
                    customer_name=row.customer_name or "",
                    document_kind="receipt_credit",
                    document_number=row.document_number or f"Receipt #{row.document_id}",
                    document_date=row.document_date,
                    due_date=None,
                    reference_text=row.reference_text,
                    description=row.description,
                    open_amount=(-unapplied_amount).quantize(Decimal("0.01")),
                    journal_entry_id=row.journal_entry_id,
                    source_document_type="customer_receipt",
                    source_document_id=int(row.document_id),
                )
            )
        return rows

    @staticmethod
    def _to_decimal(value: object) -> Decimal:
        if isinstance(value, Decimal):
            return value.quantize(Decimal("0.01"))
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))
