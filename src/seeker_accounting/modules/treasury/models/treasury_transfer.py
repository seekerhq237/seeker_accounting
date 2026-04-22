from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class TreasuryTransfer(TimestampMixin, Base):
    __tablename__ = "treasury_transfers"
    __table_args__ = (
        UniqueConstraint("company_id", "transfer_number"),
        Index("ix_treasury_transfers_company_id", "company_id"),
        Index("ix_treasury_transfers_company_id_status_code", "company_id", "status_code"),
        Index("ix_treasury_transfers_company_id_transfer_date", "company_id", "transfer_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    transfer_number: Mapped[str] = mapped_column(String(40), nullable=False)
    from_financial_account_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("financial_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    to_financial_account_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("financial_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    transfer_date: Mapped[date] = mapped_column(Date(), nullable=False)
    currency_code: Mapped[str] = mapped_column(
        String(3),
        ForeignKey("currencies.code", ondelete="RESTRICT"),
        nullable=False,
    )
    exchange_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    status_code: Mapped[str] = mapped_column(String(20), nullable=False)
    reference_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
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

    company: Mapped["Company"] = relationship("Company")
    from_financial_account: Mapped["FinancialAccount"] = relationship(
        "FinancialAccount", foreign_keys=[from_financial_account_id]
    )
    to_financial_account: Mapped["FinancialAccount"] = relationship(
        "FinancialAccount", foreign_keys=[to_financial_account_id]
    )
    currency: Mapped["Currency"] = relationship("Currency")
    posted_journal_entry: Mapped["JournalEntry | None"] = relationship("JournalEntry")
    posted_by_user: Mapped["User | None"] = relationship("User", foreign_keys=[posted_by_user_id])
