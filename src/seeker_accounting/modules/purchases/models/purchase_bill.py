from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class PurchaseBill(TimestampMixin, Base):
    __tablename__ = "purchase_bills"
    __table_args__ = (
        UniqueConstraint("company_id", "bill_number"),
        Index("ix_purchase_bills_company_id", "company_id"),
        Index("ix_purchase_bills_company_id_supplier_id_bill_date", "company_id", "supplier_id", "bill_date"),
        Index("ix_purchase_bills_company_id_status_code", "company_id", "status_code"),
        Index("ix_purchase_bills_company_id_payment_status_code", "company_id", "payment_status_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    bill_number: Mapped[str] = mapped_column(String(40), nullable=False)
    supplier_bill_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    supplier_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    bill_date: Mapped[date] = mapped_column(Date(), nullable=False)
    due_date: Mapped[date] = mapped_column(Date(), nullable=False)
    currency_code: Mapped[str] = mapped_column(
        String(3),
        ForeignKey("currencies.code", ondelete="RESTRICT"),
        nullable=False,
    )
    exchange_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    status_code: Mapped[str] = mapped_column(String(20), nullable=False)
    payment_status_code: Mapped[str] = mapped_column(String(20), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    subtotal_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    posted_journal_entry_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("journal_entries.id", ondelete="RESTRICT"),
        nullable=True,
    )
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    posted_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    contract_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("contracts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    project_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=True,
    )
    source_order_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("purchase_orders.id", ondelete="RESTRICT"),
        nullable=True,
    )

    company: Mapped["Company"] = relationship("Company")
    supplier: Mapped["Supplier"] = relationship("Supplier")
    contract: Mapped["Contract | None"] = relationship("Contract")
    project: Mapped["Project | None"] = relationship("Project")
    currency: Mapped["Currency"] = relationship("Currency")
    source_order: Mapped["PurchaseOrder | None"] = relationship(
        "PurchaseOrder",
        foreign_keys=[source_order_id],
    )
    posted_journal_entry: Mapped["JournalEntry | None"] = relationship("JournalEntry")
    posted_by_user: Mapped["User | None"] = relationship("User", foreign_keys=[posted_by_user_id])
    allocations: Mapped[list["SupplierPaymentAllocation"]] = relationship(
        "SupplierPaymentAllocation",
        back_populates="purchase_bill",
    )
    lines: Mapped[list["PurchaseBillLine"]] = relationship(
        "PurchaseBillLine",
        back_populates="purchase_bill",
        cascade="all, delete-orphan",
    )
