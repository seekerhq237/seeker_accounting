"""GRNI Accrual Report Service — uninvoiced goods receipts.

Shows posted GRN lines that have not yet been matched to a supplier bill line.
This represents the GRNI (Goods Received Not Invoiced) accrual balance.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory

_ZERO = Decimal("0")


@dataclass
class GrniLineDTO:
    inventory_document_id: int
    document_number: str | None
    receipt_date: date
    supplier_id: int | None
    supplier_name: str | None
    item_id: int | None
    item_code: str | None
    item_name: str | None
    received_qty: Decimal
    unit_cost: Decimal
    line_amount: Decimal
    days_outstanding: int


@dataclass
class GrniAccrualReportDTO:
    as_of_date: date
    company_id: int
    rows: list[GrniLineDTO]
    total_grni_balance: Decimal


class GrniAccrualReportService:
    def __init__(self, unit_of_work_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = unit_of_work_factory

    def get_report(self, company_id: int, as_of_date: date | None = None) -> GrniAccrualReportDTO:
        today = as_of_date or date.today()
        with self._uow_factory() as uow:
            return self._build(uow.session, company_id, today)

    def _build(self, session: Session, company_id: int, today: date) -> GrniAccrualReportDTO:
        from seeker_accounting.modules.inventory.models.inventory_document import InventoryDocument
        from seeker_accounting.modules.inventory.models.inventory_document_line import InventoryDocumentLine
        from seeker_accounting.modules.inventory.models.purchase_receipt_link import PurchaseBillLineReceiptLink
        from seeker_accounting.modules.inventory.models.item import Item

        # GRN lines with no bill link
        matched_line_ids_subq = select(
            PurchaseBillLineReceiptLink.inventory_document_line_id
        ).scalar_subquery()

        stmt = (
            select(InventoryDocumentLine, InventoryDocument)
            .join(InventoryDocument, InventoryDocument.id == InventoryDocumentLine.inventory_document_id)
            .where(
                InventoryDocument.company_id == company_id,
                InventoryDocument.document_type_code == "goods_receipt_purchase",
                InventoryDocument.status_code == "posted",
                InventoryDocumentLine.id.not_in(matched_line_ids_subq),
            )
            .order_by(InventoryDocument.document_date)
        )

        items_map = {
            row.id: (row.item_code, row.item_name)
            for row in session.scalars(select(Item).where(Item.company_id == company_id))
        }

        # Supplier names — lazy load via counterparty model
        supplier_names = self._load_supplier_names(session, company_id)

        rows: list[GrniLineDTO] = []
        total = _ZERO
        for line, doc in session.execute(stmt):
            doc_date = doc.document_date or today
            days_out = (today - doc_date).days if isinstance(doc_date, date) else 0
            code, name = items_map.get(line.item_id, (None, None)) if line.item_id else (None, None)
            sup_id = doc.supplier_id if hasattr(doc, "supplier_id") else None
            sup_name = supplier_names.get(sup_id) if sup_id else None
            line_amt = Decimal(str(line.line_amount)) if line.line_amount else _ZERO
            rows.append(
                GrniLineDTO(
                    inventory_document_id=doc.id,
                    document_number=doc.document_number,
                    receipt_date=doc_date,
                    supplier_id=sup_id,
                    supplier_name=sup_name,
                    item_id=line.item_id,
                    item_code=code,
                    item_name=name,
                    received_qty=Decimal(str(line.quantity)) if line.quantity else _ZERO,
                    unit_cost=Decimal(str(line.unit_cost)) if line.unit_cost else _ZERO,
                    line_amount=line_amt,
                    days_outstanding=days_out,
                )
            )
            total += line_amt

        return GrniAccrualReportDTO(
            as_of_date=today,
            company_id=company_id,
            rows=rows,
            total_grni_balance=total,
        )

    def _load_supplier_names(self, session: Session, company_id: int) -> dict[int, str]:
        try:
            from seeker_accounting.modules.suppliers.models.supplier import Supplier
            stmt = select(Supplier.id, Supplier.display_name).where(
                Supplier.company_id == company_id
            )
            return {row.id: row.display_name for row in session.execute(stmt)}
        except Exception:
            return {}
