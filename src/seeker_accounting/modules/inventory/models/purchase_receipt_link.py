"""Three-way match link tables for GRN workflow (P2 / Slice 3.3).

PurchaseOrderLineReceiptLink  — ties a PO line to specific GRN document lines,
                                tracking received qty.
PurchaseBillLineReceiptLink   — ties a supplier bill line to GRN document lines,
                                tracking matched qty and value (enables GRNI clearing
                                and purchase-price-variance calculation).
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    Numeric,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from seeker_accounting.modules.inventory.models.inventory_document_line import (
        InventoryDocumentLine,
    )
    from seeker_accounting.modules.purchases.models.purchase_bill_line import PurchaseBillLine
    from seeker_accounting.modules.purchases.models.purchase_order_line import PurchaseOrderLine


class PurchaseOrderLineReceiptLink(TimestampMixin, Base):
    """Quantity received against a PO line on a specific GRN line."""

    __tablename__ = "purchase_order_line_receipt_links"
    __table_args__ = (
        UniqueConstraint(
            "purchase_order_line_id",
            "inventory_document_line_id",
            name="uq_po_receipt_link",
        ),
        Index("ix_po_receipt_links_company_id", "company_id"),
        Index("ix_po_receipt_links_po_line_id", "purchase_order_line_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False
    )
    purchase_order_line_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("purchase_order_lines.id", ondelete="RESTRICT"),
        nullable=False,
    )
    inventory_document_line_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("inventory_document_lines.id", ondelete="RESTRICT"),
        nullable=False,
    )
    received_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)

    purchase_order_line: Mapped["PurchaseOrderLine"] = relationship(
        "PurchaseOrderLine", foreign_keys=[purchase_order_line_id]
    )
    inventory_document_line: Mapped["InventoryDocumentLine"] = relationship(
        "InventoryDocumentLine", foreign_keys=[inventory_document_line_id]
    )


class PurchaseBillLineReceiptLink(TimestampMixin, Base):
    """Quantity and value matched between a supplier bill line and a GRN line.

    When a bill line matches to a receipt:
      Dr GRNI (clearing)   @ GRN cost
      Cr AP                @ bill cost
      Dr/Cr PPV            @ difference (purchase-price variance)
    """

    __tablename__ = "purchase_bill_line_receipt_links"
    __table_args__ = (
        UniqueConstraint(
            "purchase_bill_line_id",
            "inventory_document_line_id",
            name="uq_bill_receipt_link",
        ),
        Index("ix_bill_receipt_links_company_id", "company_id"),
        Index("ix_bill_receipt_links_bill_line_id", "purchase_bill_line_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False
    )
    purchase_bill_line_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("purchase_bill_lines.id", ondelete="RESTRICT"),
        nullable=False,
    )
    inventory_document_line_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("inventory_document_lines.id", ondelete="RESTRICT"),
        nullable=False,
    )
    matched_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    matched_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    purchase_bill_line: Mapped["PurchaseBillLine"] = relationship(
        "PurchaseBillLine", foreign_keys=[purchase_bill_line_id]
    )
    inventory_document_line: Mapped["InventoryDocumentLine"] = relationship(
        "InventoryDocumentLine", foreign_keys=[inventory_document_line_id]
    )
