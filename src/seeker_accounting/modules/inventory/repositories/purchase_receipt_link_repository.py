"""Repository for GRN three-way match link tables (P2 / Slice 3.3)."""

from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.inventory.models.purchase_receipt_link import (
    PurchaseBillLineReceiptLink,
    PurchaseOrderLineReceiptLink,
)


class PurchaseReceiptLinkRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # PO line receipt links
    # ------------------------------------------------------------------

    def list_po_links_for_document(
        self, inventory_document_line_id: int
    ) -> Sequence[PurchaseOrderLineReceiptLink]:
        stmt = select(PurchaseOrderLineReceiptLink).where(
            PurchaseOrderLineReceiptLink.inventory_document_line_id
            == inventory_document_line_id
        )
        return self._session.scalars(stmt).all()

    def list_po_links_for_order_line(
        self, company_id: int, po_line_id: int
    ) -> Sequence[PurchaseOrderLineReceiptLink]:
        stmt = select(PurchaseOrderLineReceiptLink).where(
            PurchaseOrderLineReceiptLink.company_id == company_id,
            PurchaseOrderLineReceiptLink.purchase_order_line_id == po_line_id,
        )
        return self._session.scalars(stmt).all()

    def sum_received_qty_for_po_line(self, company_id: int, po_line_id: int) -> Decimal:
        rows = self.list_po_links_for_order_line(company_id, po_line_id)
        return sum((r.received_qty for r in rows), Decimal("0"))

    def add_po_link(self, link: PurchaseOrderLineReceiptLink) -> None:
        self._session.add(link)

    # ------------------------------------------------------------------
    # Bill line receipt links
    # ------------------------------------------------------------------

    def list_bill_links_for_document(
        self, inventory_document_line_id: int
    ) -> Sequence[PurchaseBillLineReceiptLink]:
        stmt = select(PurchaseBillLineReceiptLink).where(
            PurchaseBillLineReceiptLink.inventory_document_line_id
            == inventory_document_line_id
        )
        return self._session.scalars(stmt).all()

    def list_bill_links_for_bill_line(
        self, company_id: int, bill_line_id: int
    ) -> Sequence[PurchaseBillLineReceiptLink]:
        stmt = select(PurchaseBillLineReceiptLink).where(
            PurchaseBillLineReceiptLink.company_id == company_id,
            PurchaseBillLineReceiptLink.purchase_bill_line_id == bill_line_id,
        )
        return self._session.scalars(stmt).all()

    def add_bill_link(self, link: PurchaseBillLineReceiptLink) -> None:
        self._session.add(link)
