from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class ProductionOrder(TimestampMixin, Base):
    """Light manufacturing order tying a BOM to component issue and receipt docs."""

    __tablename__ = "production_orders"
    __table_args__ = (
        Index("ix_production_orders_company_status", "company_id", "status_code"),
        Index("ix_production_orders_bom_id", "bom_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False
    )
    order_number: Mapped[str] = mapped_column(String(40), nullable=False)
    bom_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("bills_of_material.id", ondelete="RESTRICT"), nullable=False
    )
    finished_item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("items.id", ondelete="RESTRICT"), nullable=False
    )
    location_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("inventory_locations.id", ondelete="RESTRICT"), nullable=True
    )
    order_date: Mapped[date] = mapped_column(Date(), nullable=False)
    quantity_to_produce: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    status_code: Mapped[str] = mapped_column(
        String(30), nullable=False, default="draft", server_default="draft"
    )
    component_issue_document_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("inventory_documents.id", ondelete="RESTRICT"), nullable=True
    )
    finished_receipt_document_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("inventory_documents.id", ondelete="RESTRICT"), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    completed_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    company: Mapped["Company"] = relationship("Company")
    bom: Mapped["BillOfMaterial"] = relationship("BillOfMaterial")
    finished_item: Mapped["Item"] = relationship("Item")
    location: Mapped["InventoryLocation | None"] = relationship("InventoryLocation")
    component_issue_document: Mapped["InventoryDocument | None"] = relationship(
        "InventoryDocument", foreign_keys=[component_issue_document_id]
    )
    finished_receipt_document: Mapped["InventoryDocument | None"] = relationship(
        "InventoryDocument", foreign_keys=[finished_receipt_document_id]
    )
    completed_by_user: Mapped["User | None"] = relationship("User")
