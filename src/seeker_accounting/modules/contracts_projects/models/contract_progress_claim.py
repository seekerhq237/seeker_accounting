from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class ContractProgressClaim(TimestampMixin, Base):
    __tablename__ = "contract_progress_claims"
    __table_args__ = (
        UniqueConstraint("company_id", "claim_number"),
        Index("ix_contract_progress_claims_company_id", "company_id"),
        Index("ix_contract_progress_claims_contract_id", "contract_id"),
        Index("ix_contract_progress_claims_sales_invoice_id", "sales_invoice_id"),
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
    claim_number: Mapped[str] = mapped_column(String(40), nullable=False)
    claim_date: Mapped[date] = mapped_column(Date(), nullable=False)
    status_code: Mapped[str] = mapped_column(String(20), nullable=False)
    billing_schedule_item_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("contract_billing_schedule_items.id", ondelete="RESTRICT"),
        nullable=True,
    )
    sales_invoice_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("sales_invoices.id", ondelete="RESTRICT"),
        nullable=True,
    )
    taxable_base_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    previous_certified_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    current_claim_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    certified_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    earned_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    vat_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    retention_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    retention_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    advance_recovery_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    withheld_vat_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    withholding_tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    net_receivable_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    source_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    certified_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    certified_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    company: Mapped["Company"] = relationship("Company")
    contract: Mapped["Contract"] = relationship("Contract")
    billing_schedule_item: Mapped["ContractBillingScheduleItem | None"] = relationship("ContractBillingScheduleItem")
    sales_invoice: Mapped["SalesInvoice | None"] = relationship("SalesInvoice")
    certified_by_user: Mapped["User | None"] = relationship("User", foreign_keys=[certified_by_user_id])
    lines: Mapped[list["ContractProgressClaimLine"]] = relationship(
        "ContractProgressClaimLine",
        back_populates="progress_claim",
        cascade="all, delete-orphan",
    )
