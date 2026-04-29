"""Tax payment — money paid against a tax return.

A return can be settled by one or more payments. The journal-entry
link is optional so the slice can land before journal posting is
fully wired (Phase 2 of the blueprint).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class TaxPayment(TimestampMixin, Base):
    __tablename__ = "tax_payments"
    __table_args__ = (
        Index("ix_tax_payments_company_id", "company_id"),
        Index("ix_tax_payments_return_id", "tax_return_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    tax_return_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("tax_returns.id", ondelete="RESTRICT"),
        nullable=True,
    )
    payment_date: Mapped[date] = mapped_column(Date(), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    payment_method_code: Mapped[str] = mapped_column(String(50), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    journal_entry_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("journal_entries.id", ondelete="SET NULL"),
        nullable=True,
    )
    recorded_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    tax_return: Mapped["TaxReturn | None"] = relationship(
        "TaxReturn", back_populates="payments"
    )
