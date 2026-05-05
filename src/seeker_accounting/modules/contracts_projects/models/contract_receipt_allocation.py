from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class ContractReceiptAllocation(TimestampMixin, Base):
    __tablename__ = "contract_receipt_allocations"
    __table_args__ = (
        Index("ix_contract_receipt_allocations_company_id", "company_id"),
        Index("ix_contract_receipt_allocations_contract_id", "contract_id"),
        Index("ix_contract_receipt_allocations_receipt_id", "customer_receipt_id"),
        Index("ix_contract_receipt_allocations_invoice_id", "sales_invoice_id"),
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
    customer_receipt_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("customer_receipts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    sales_invoice_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("sales_invoices.id", ondelete="RESTRICT"),
        nullable=True,
    )
    progress_claim_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("contract_progress_claims.id", ondelete="RESTRICT"),
        nullable=True,
    )
    allocation_date: Mapped[date] = mapped_column(Date(), nullable=False)
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    net_receivable_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    withholding_vat_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    withholding_tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    retention_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    advance_recovery_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    total_allocated_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    company: Mapped["Company"] = relationship("Company")
    contract: Mapped["Contract"] = relationship("Contract")
    customer_receipt: Mapped["CustomerReceipt | None"] = relationship("CustomerReceipt")
    sales_invoice: Mapped["SalesInvoice | None"] = relationship("SalesInvoice")
    progress_claim: Mapped["ContractProgressClaim | None"] = relationship("ContractProgressClaim")
