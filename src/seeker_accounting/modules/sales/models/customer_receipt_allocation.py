from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, utcnow


class CustomerReceiptAllocation(Base):
    __tablename__ = "customer_receipt_allocations"
    __table_args__ = (
        UniqueConstraint("customer_receipt_id", "sales_invoice_id"),
        Index("ix_customer_receipt_allocations_sales_invoice_id", "sales_invoice_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    customer_receipt_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("customer_receipts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sales_invoice_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sales_invoices.id", ondelete="RESTRICT"),
        nullable=False,
    )
    allocated_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    allocation_date: Mapped[date] = mapped_column(Date(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)

    customer_receipt: Mapped["CustomerReceipt"] = relationship("CustomerReceipt", back_populates="allocations")
    sales_invoice: Mapped["SalesInvoice"] = relationship("SalesInvoice", back_populates="allocations")
