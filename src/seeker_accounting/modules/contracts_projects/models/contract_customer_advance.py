from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class ContractCustomerAdvance(TimestampMixin, Base):
    __tablename__ = "contract_customer_advances"
    __table_args__ = (
        UniqueConstraint("company_id", "advance_number"),
        Index("ix_contract_customer_advances_company_id", "company_id"),
        Index("ix_contract_customer_advances_contract_id", "contract_id"),
        Index("ix_contract_customer_advances_receipt_id", "customer_receipt_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    contract_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("contracts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    advance_number: Mapped[str] = mapped_column(String(40), nullable=False)
    advance_date: Mapped[date] = mapped_column(Date(), nullable=False)
    status_code: Mapped[str] = mapped_column(String(20), nullable=False)
    source_invoice_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("sales_invoices.id", ondelete="RESTRICT"),
        nullable=True,
    )
    customer_receipt_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("customer_receipts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    advance_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    received_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    recovery_basis_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    recovery_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    company: Mapped["Company"] = relationship("Company")
    contract: Mapped["Contract"] = relationship("Contract")
    source_invoice: Mapped["SalesInvoice | None"] = relationship("SalesInvoice")
    customer_receipt: Mapped["CustomerReceipt | None"] = relationship("CustomerReceipt")
