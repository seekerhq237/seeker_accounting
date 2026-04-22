from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class SalesInvoice(TimestampMixin, Base):
    __tablename__ = "sales_invoices"
    __table_args__ = (
        UniqueConstraint("company_id", "invoice_number"),
        Index("ix_sales_invoices_company_id", "company_id"),
        Index("ix_sales_invoices_company_id_customer_id_invoice_date", "company_id", "customer_id", "invoice_date"),
        Index("ix_sales_invoices_company_id_payment_status_code", "company_id", "payment_status_code"),
        Index("ix_sales_invoices_company_id_status_code", "company_id", "status_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    invoice_number: Mapped[str] = mapped_column(String(40), nullable=False)
    customer_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    invoice_date: Mapped[date] = mapped_column(Date(), nullable=False)
    due_date: Mapped[date] = mapped_column(Date(), nullable=False)
    currency_code: Mapped[str] = mapped_column(
        String(3),
        ForeignKey("currencies.code", ondelete="RESTRICT"),
        nullable=False,
    )
    exchange_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    status_code: Mapped[str] = mapped_column(String(20), nullable=False)
    payment_status_code: Mapped[str] = mapped_column(String(20), nullable=False)
    reference_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
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
    source_quote_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("customer_quotes.id", ondelete="RESTRICT"),
        nullable=True,
    )
    source_order_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("sales_orders.id", ondelete="RESTRICT"),
        nullable=True,
    )

    company: Mapped["Company"] = relationship("Company")
    customer: Mapped["Customer"] = relationship("Customer")
    contract: Mapped["Contract | None"] = relationship("Contract")
    project: Mapped["Project | None"] = relationship("Project")
    currency: Mapped["Currency"] = relationship("Currency")
    posted_journal_entry: Mapped["JournalEntry | None"] = relationship("JournalEntry")
    posted_by_user: Mapped["User | None"] = relationship("User", foreign_keys=[posted_by_user_id])
    source_quote: Mapped["CustomerQuote | None"] = relationship(
        "CustomerQuote",
        foreign_keys=[source_quote_id],
    )
    source_order: Mapped["SalesOrder | None"] = relationship(
        "SalesOrder",
        foreign_keys=[source_order_id],
    )
    allocations: Mapped[list["CustomerReceiptAllocation"]] = relationship(
        "CustomerReceiptAllocation",
        back_populates="sales_invoice",
    )
    lines: Mapped[list["SalesInvoiceLine"]] = relationship(
        "SalesInvoiceLine",
        back_populates="sales_invoice",
        cascade="all, delete-orphan",
    )
