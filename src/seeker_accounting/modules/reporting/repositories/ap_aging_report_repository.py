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
from seeker_accounting.modules.purchases.models.purchase_bill import PurchaseBill
from seeker_accounting.modules.purchases.models.supplier_payment import SupplierPayment
from seeker_accounting.modules.purchases.models.supplier_payment_allocation import (
    SupplierPaymentAllocation,
)
from seeker_accounting.modules.suppliers.models.supplier import Supplier


@dataclass(frozen=True, slots=True)
class APAgingDocumentRow:
    supplier_id: int
    supplier_code: str
    supplier_name: str
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


class APAgingReportRepository:
    """Query-only repository for AP aging and supporting supplier detail."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_open_documents(self, company_id: int, as_of_date: date) -> list[APAgingDocumentRow]:
        rows = [
            *self._list_open_bill_rows(company_id, as_of_date),
            *self._list_unapplied_payment_rows(company_id, as_of_date),
        ]
        rows.sort(key=lambda row: (row.supplier_name.lower(), row.supplier_code, row.document_date, row.document_number))
        return rows

    def get_supplier_identity(self, company_id: int, supplier_id: int) -> tuple[str, str] | None:
        stmt = select(Supplier.supplier_code, Supplier.display_name).where(
            Supplier.company_id == company_id,
            Supplier.id == supplier_id,
        )
        row = self._session.execute(stmt).one_or_none()
        if row is None:
            return None
        return row.supplier_code, row.display_name

    def sum_control_balance(self, company_id: int, as_of_date: date) -> Decimal | None:
        mapping_stmt = select(AccountRoleMapping.account_id).where(
            AccountRoleMapping.company_id == company_id,
            AccountRoleMapping.role_code == "ap_control",
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
        return (self._to_decimal(row.credit) - self._to_decimal(row.debit)).quantize(Decimal("0.01"))

    def _list_open_bill_rows(self, company_id: int, as_of_date: date) -> list[APAgingDocumentRow]:
        allocation_subquery = (
            select(
                SupplierPaymentAllocation.purchase_bill_id.label("bill_id"),
                func.coalesce(func.sum(SupplierPaymentAllocation.allocated_amount), 0).label("allocated_amount"),
            )
            .join(SupplierPayment, SupplierPayment.id == SupplierPaymentAllocation.supplier_payment_id)
            .where(
                SupplierPaymentAllocation.company_id == company_id,
                SupplierPayment.status_code == "posted",
                SupplierPaymentAllocation.allocation_date <= as_of_date,
            )
            .group_by(SupplierPaymentAllocation.purchase_bill_id)
            .subquery()
        )
        stmt = (
            select(
                PurchaseBill.id.label("document_id"),
                PurchaseBill.bill_number.label("document_number"),
                PurchaseBill.bill_date.label("document_date"),
                PurchaseBill.due_date.label("due_date"),
                PurchaseBill.supplier_bill_reference.label("reference_text"),
                PurchaseBill.notes.label("description"),
                PurchaseBill.total_amount.label("gross_amount"),
                func.coalesce(allocation_subquery.c.allocated_amount, 0).label("allocated_amount"),
                PurchaseBill.posted_journal_entry_id.label("journal_entry_id"),
                Supplier.id.label("supplier_id"),
                Supplier.supplier_code.label("supplier_code"),
                Supplier.display_name.label("supplier_name"),
            )
            .join(Supplier, Supplier.id == PurchaseBill.supplier_id)
            .outerjoin(allocation_subquery, allocation_subquery.c.bill_id == PurchaseBill.id)
            .where(
                PurchaseBill.company_id == company_id,
                PurchaseBill.status_code == "posted",
                PurchaseBill.bill_date <= as_of_date,
            )
        )
        rows: list[APAgingDocumentRow] = []
        for row in self._session.execute(stmt):
            open_amount = self._to_decimal(row.gross_amount) - self._to_decimal(row.allocated_amount)
            if open_amount <= Decimal("0.00"):
                continue
            rows.append(
                APAgingDocumentRow(
                    supplier_id=int(row.supplier_id),
                    supplier_code=row.supplier_code or "",
                    supplier_name=row.supplier_name or "",
                    document_kind="bill",
                    document_number=row.document_number or f"Bill #{row.document_id}",
                    document_date=row.document_date,
                    due_date=row.due_date,
                    reference_text=row.reference_text,
                    description=row.description,
                    open_amount=open_amount.quantize(Decimal("0.01")),
                    journal_entry_id=row.journal_entry_id,
                    source_document_type="purchase_bill",
                    source_document_id=int(row.document_id),
                )
            )
        return rows

    def _list_unapplied_payment_rows(self, company_id: int, as_of_date: date) -> list[APAgingDocumentRow]:
        allocation_subquery = (
            select(
                SupplierPaymentAllocation.supplier_payment_id.label("payment_id"),
                func.coalesce(func.sum(SupplierPaymentAllocation.allocated_amount), 0).label("allocated_amount"),
            )
            .where(
                SupplierPaymentAllocation.company_id == company_id,
                SupplierPaymentAllocation.allocation_date <= as_of_date,
            )
            .group_by(SupplierPaymentAllocation.supplier_payment_id)
            .subquery()
        )
        stmt = (
            select(
                SupplierPayment.id.label("document_id"),
                SupplierPayment.payment_number.label("document_number"),
                SupplierPayment.payment_date.label("document_date"),
                SupplierPayment.reference_number.label("reference_text"),
                SupplierPayment.notes.label("description"),
                SupplierPayment.amount_paid.label("gross_amount"),
                func.coalesce(allocation_subquery.c.allocated_amount, 0).label("allocated_amount"),
                SupplierPayment.posted_journal_entry_id.label("journal_entry_id"),
                Supplier.id.label("supplier_id"),
                Supplier.supplier_code.label("supplier_code"),
                Supplier.display_name.label("supplier_name"),
            )
            .join(Supplier, Supplier.id == SupplierPayment.supplier_id)
            .outerjoin(allocation_subquery, allocation_subquery.c.payment_id == SupplierPayment.id)
            .where(
                SupplierPayment.company_id == company_id,
                SupplierPayment.status_code == "posted",
                SupplierPayment.payment_date <= as_of_date,
            )
        )
        rows: list[APAgingDocumentRow] = []
        for row in self._session.execute(stmt):
            unapplied_amount = self._to_decimal(row.gross_amount) - self._to_decimal(row.allocated_amount)
            if unapplied_amount <= Decimal("0.00"):
                continue
            rows.append(
                APAgingDocumentRow(
                    supplier_id=int(row.supplier_id),
                    supplier_code=row.supplier_code or "",
                    supplier_name=row.supplier_name or "",
                    document_kind="payment_credit",
                    document_number=row.document_number or f"Payment #{row.document_id}",
                    document_date=row.document_date,
                    due_date=None,
                    reference_text=row.reference_text,
                    description=row.description,
                    open_amount=(-unapplied_amount).quantize(Decimal("0.01")),
                    journal_entry_id=row.journal_entry_id,
                    source_document_type="supplier_payment",
                    source_document_id=int(row.document_id),
                )
            )
        return rows

    @staticmethod
    def _to_decimal(value: object) -> Decimal:
        if isinstance(value, Decimal):
            return value.quantize(Decimal("0.01"))
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))
