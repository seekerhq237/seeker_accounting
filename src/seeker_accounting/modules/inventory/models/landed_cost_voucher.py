"""Landed cost vouchers (P5 / Slice 6.2).

Captures import-related charges (freight, duty, insurance, other) and allocates
them across the linked GRNs.  Posting creates revaluation entries in the stock
ledger and posts a journal entry: Dr Inventory / Cr AP (or Cr Cash).

allocation_basis_code choices: 'by_value', 'by_qty', 'by_weight', 'manual'
status_code choices: 'draft', 'posted'
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from seeker_accounting.modules.inventory.models.inventory_document import InventoryDocument


class LandedCostVoucher(TimestampMixin, Base):
    """Header for a landed-cost allocation voucher."""

    __tablename__ = "landed_cost_vouchers"
    __table_args__ = (
        UniqueConstraint("company_id", "voucher_number", name="uq_landed_cost_vouchers"),
        Index("ix_landed_cost_vouchers_company", "company_id"),
        Index("ix_landed_cost_vouchers_status", "company_id", "status_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False
    )
    voucher_number: Mapped[str] = mapped_column(String(40), nullable=False)
    voucher_date: Mapped[date] = mapped_column(Date(), nullable=False)
    declaration_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    total_freight: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0")
    )
    total_duty: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0")
    )
    total_insurance: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0")
    )
    total_other: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0")
    )
    allocation_basis_code: Mapped[str] = mapped_column(
        String(20), nullable=False, default="by_value"
    )
    status_code: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    posted_journal_entry_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("journal_entries.id", ondelete="RESTRICT"),
        nullable=True,
    )
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    posted_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )

    receipts: Mapped[list["LandedCostVoucherReceipt"]] = relationship(
        "LandedCostVoucherReceipt",
        back_populates="voucher",
        cascade="all, delete-orphan",
    )

    @property
    def total_landed_cost(self) -> Decimal:
        return (
            self.total_freight + self.total_duty + self.total_insurance + self.total_other
        )


class LandedCostVoucherReceipt(TimestampMixin, Base):
    """Links a GRN to a landed cost voucher with the computed allocation."""

    __tablename__ = "landed_cost_voucher_receipts"
    __table_args__ = (
        UniqueConstraint("voucher_id", "inventory_document_id", name="uq_lcv_receipts"),
        Index("ix_lcv_receipts_voucher_id", "voucher_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    voucher_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("landed_cost_vouchers.id", ondelete="RESTRICT"), nullable=False
    )
    inventory_document_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("inventory_documents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    allocated_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    allocation_weight: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)

    voucher: Mapped["LandedCostVoucher"] = relationship(
        "LandedCostVoucher", back_populates="receipts"
    )
    inventory_document: Mapped["InventoryDocument"] = relationship(
        "InventoryDocument", foreign_keys=[inventory_document_id]
    )
