from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class ContractRetentionMovement(TimestampMixin, Base):
    __tablename__ = "contract_retention_movements"
    __table_args__ = (
        Index("ix_contract_retention_movements_company_id", "company_id"),
        Index("ix_contract_retention_movements_contract_id", "contract_id"),
        Index("ix_contract_retention_movements_claim_id", "progress_claim_id"),
        Index("ix_contract_retention_movements_invoice_id", "sales_invoice_id"),
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
    progress_claim_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("contract_progress_claims.id", ondelete="RESTRICT"),
        nullable=True,
    )
    sales_invoice_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("sales_invoices.id", ondelete="RESTRICT"),
        nullable=True,
    )
    customer_receipt_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("customer_receipts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    movement_date: Mapped[date] = mapped_column(Date(), nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    movement_type_code: Mapped[str] = mapped_column(String(30), nullable=False)
    status_code: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    company: Mapped["Company"] = relationship("Company")
    contract: Mapped["Contract"] = relationship("Contract")
    progress_claim: Mapped["ContractProgressClaim | None"] = relationship("ContractProgressClaim")
    sales_invoice: Mapped["SalesInvoice | None"] = relationship("SalesInvoice")
    customer_receipt: Mapped["CustomerReceipt | None"] = relationship("CustomerReceipt")
