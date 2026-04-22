from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, utcnow


class SupplierPaymentAllocation(Base):
    __tablename__ = "supplier_payment_allocations"
    __table_args__ = (
        UniqueConstraint("supplier_payment_id", "purchase_bill_id"),
        Index("ix_supplier_payment_allocations_purchase_bill_id", "purchase_bill_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    supplier_payment_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("supplier_payments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    purchase_bill_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("purchase_bills.id", ondelete="RESTRICT"),
        nullable=False,
    )
    allocated_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    allocation_date: Mapped[date] = mapped_column(Date(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)

    supplier_payment: Mapped["SupplierPayment"] = relationship("SupplierPayment", back_populates="allocations")
    purchase_bill: Mapped["PurchaseBill"] = relationship("PurchaseBill", back_populates="allocations")
