"""Tax return model.

A formal filing produced for a tax obligation. The header carries
status, totals, and external filing references; the breakdown into
statutory boxes lives on ``TaxReturnLine``.

Returns are generated from posted source documents (sales invoices,
purchase bills, payroll runs, treasury settlements) plus explicit
adjustment entries. Draft returns can be regenerated; filed returns
become immutable in normal flows.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class TaxReturn(TimestampMixin, Base):
    __tablename__ = "tax_returns"
    __table_args__ = (
        Index("ix_tax_returns_company_id", "company_id"),
        Index("ix_tax_returns_obligation_id", "obligation_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    obligation_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tax_obligations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    tax_type_code: Mapped[str] = mapped_column(String(50), nullable=False)
    period_start: Mapped[date] = mapped_column(Date(), nullable=False)
    period_end: Mapped[date] = mapped_column(Date(), nullable=False)
    status_code: Mapped[str] = mapped_column(
        String(30), nullable=False, default="DRAFT"
    )
    total_due_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0.00")
    )
    total_paid_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0.00")
    )
    filed_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    otp_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    external_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    prepared_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    journal_entry_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("journal_entries.id", ondelete="RESTRICT"),
        nullable=True,
    )

    obligation: Mapped["TaxObligation"] = relationship(
        "TaxObligation", back_populates="tax_returns"
    )
    lines: Mapped[list["TaxReturnLine"]] = relationship(
        "TaxReturnLine",
        back_populates="tax_return",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    payments: Mapped[list["TaxPayment"]] = relationship(
        "TaxPayment",
        back_populates="tax_return",
        passive_deletes=True,
    )
