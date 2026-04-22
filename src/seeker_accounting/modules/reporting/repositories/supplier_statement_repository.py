from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.purchases.models.purchase_bill import PurchaseBill
from seeker_accounting.modules.purchases.models.supplier_payment import SupplierPayment
from seeker_accounting.modules.suppliers.models.supplier import Supplier


@dataclass(frozen=True, slots=True)
class SupplierStatementMovementRow:
    movement_date: date
    movement_kind: str
    document_number: str
    reference_text: str | None
    description: str | None
    bill_amount: Decimal
    payment_amount: Decimal
    journal_entry_id: int | None
    source_document_type: str
    source_document_id: int


class SupplierStatementRepository:
    """Query-only repository for supplier statement reporting."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_supplier_identity(self, company_id: int, supplier_id: int) -> tuple[str, str] | None:
        stmt = select(Supplier.supplier_code, Supplier.display_name).where(
            Supplier.company_id == company_id,
            Supplier.id == supplier_id,
        )
        row = self._session.execute(stmt).one_or_none()
        if row is None:
            return None
        return row.supplier_code, row.display_name

    def sum_opening_balance(
        self,
        company_id: int,
        supplier_id: int,
        date_from: date | None,
    ) -> Decimal:
        if date_from is None:
            return Decimal("0.00")

        bill_stmt = select(func.coalesce(func.sum(PurchaseBill.total_amount), 0)).where(
            PurchaseBill.company_id == company_id,
            PurchaseBill.supplier_id == supplier_id,
            PurchaseBill.status_code == "posted",
            PurchaseBill.bill_date < date_from,
        )
        payment_stmt = select(func.coalesce(func.sum(SupplierPayment.amount_paid), 0)).where(
            SupplierPayment.company_id == company_id,
            SupplierPayment.supplier_id == supplier_id,
            SupplierPayment.status_code == "posted",
            SupplierPayment.payment_date < date_from,
        )
        bill_total = self._to_decimal(self._session.scalar(bill_stmt))
        payment_total = self._to_decimal(self._session.scalar(payment_stmt))
        return (bill_total - payment_total).quantize(Decimal("0.01"))

    def list_period_movements(
        self,
        company_id: int,
        supplier_id: int,
        date_from: date | None,
        date_to: date | None,
    ) -> list[SupplierStatementMovementRow]:
        rows = [
            *self._list_bill_rows(company_id, supplier_id, date_from, date_to),
            *self._list_payment_rows(company_id, supplier_id, date_from, date_to),
        ]
        rows.sort(
            key=lambda row: (
                row.movement_date,
                0 if row.movement_kind == "bill" else 1,
                row.document_number,
            )
        )
        return rows

    def _list_bill_rows(
        self,
        company_id: int,
        supplier_id: int,
        date_from: date | None,
        date_to: date | None,
    ) -> list[SupplierStatementMovementRow]:
        stmt = select(
            PurchaseBill.id.label("document_id"),
            PurchaseBill.bill_number.label("document_number"),
            PurchaseBill.bill_date.label("movement_date"),
            PurchaseBill.supplier_bill_reference.label("reference_text"),
            PurchaseBill.notes.label("description"),
            PurchaseBill.total_amount.label("bill_amount"),
            PurchaseBill.posted_journal_entry_id.label("journal_entry_id"),
        ).where(
            PurchaseBill.company_id == company_id,
            PurchaseBill.supplier_id == supplier_id,
            PurchaseBill.status_code == "posted",
        )
        if date_from is not None:
            stmt = stmt.where(PurchaseBill.bill_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(PurchaseBill.bill_date <= date_to)
        stmt = stmt.order_by(PurchaseBill.bill_date.asc(), PurchaseBill.bill_number.asc(), PurchaseBill.id.asc())
        return [
            SupplierStatementMovementRow(
                movement_date=row.movement_date,
                movement_kind="bill",
                document_number=row.document_number or f"Bill #{row.document_id}",
                reference_text=row.reference_text,
                description=row.description,
                bill_amount=self._to_decimal(row.bill_amount),
                payment_amount=Decimal("0.00"),
                journal_entry_id=row.journal_entry_id,
                source_document_type="purchase_bill",
                source_document_id=int(row.document_id),
            )
            for row in self._session.execute(stmt)
        ]

    def _list_payment_rows(
        self,
        company_id: int,
        supplier_id: int,
        date_from: date | None,
        date_to: date | None,
    ) -> list[SupplierStatementMovementRow]:
        stmt = select(
            SupplierPayment.id.label("document_id"),
            SupplierPayment.payment_number.label("document_number"),
            SupplierPayment.payment_date.label("movement_date"),
            SupplierPayment.reference_number.label("reference_text"),
            SupplierPayment.notes.label("description"),
            SupplierPayment.amount_paid.label("payment_amount"),
            SupplierPayment.posted_journal_entry_id.label("journal_entry_id"),
        ).where(
            SupplierPayment.company_id == company_id,
            SupplierPayment.supplier_id == supplier_id,
            SupplierPayment.status_code == "posted",
        )
        if date_from is not None:
            stmt = stmt.where(SupplierPayment.payment_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(SupplierPayment.payment_date <= date_to)
        stmt = stmt.order_by(
            SupplierPayment.payment_date.asc(),
            SupplierPayment.payment_number.asc(),
            SupplierPayment.id.asc(),
        )
        return [
            SupplierStatementMovementRow(
                movement_date=row.movement_date,
                movement_kind="payment",
                document_number=row.document_number or f"Payment #{row.document_id}",
                reference_text=row.reference_text,
                description=row.description,
                bill_amount=Decimal("0.00"),
                payment_amount=self._to_decimal(row.payment_amount),
                journal_entry_id=row.journal_entry_id,
                source_document_type="supplier_payment",
                source_document_id=int(row.document_id),
            )
            for row in self._session.execute(stmt)
        ]

    @staticmethod
    def _to_decimal(value: object) -> Decimal:
        if isinstance(value, Decimal):
            return value.quantize(Decimal("0.01"))
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))
