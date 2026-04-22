from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, utcnow


class BankReconciliationSession(Base):
    __tablename__ = "bank_reconciliation_sessions"
    __table_args__ = (
        Index("ix_bank_reconciliation_sessions_company_id", "company_id"),
        Index(
            "ix_bank_reconciliation_sessions_company_id_financial_account_id",
            "company_id",
            "financial_account_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    financial_account_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("financial_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    statement_end_date: Mapped[date] = mapped_column(Date(), nullable=False)
    statement_ending_balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0.00")
    )
    status_code: Mapped[str] = mapped_column(String(20), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    completed_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )

    company: Mapped["Company"] = relationship("Company")
    financial_account: Mapped["FinancialAccount"] = relationship("FinancialAccount")
    completed_by_user: Mapped["User | None"] = relationship("User", foreign_keys=[completed_by_user_id])
    created_by_user: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_user_id])
    matches: Mapped[list["BankReconciliationMatch"]] = relationship(
        "BankReconciliationMatch",
        back_populates="reconciliation_session",
        cascade="all, delete-orphan",
    )
