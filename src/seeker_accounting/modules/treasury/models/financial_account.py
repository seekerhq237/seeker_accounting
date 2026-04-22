from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import ActiveFlagMixin, Base, TimestampMixin


class FinancialAccount(TimestampMixin, ActiveFlagMixin, Base):
    __tablename__ = "financial_accounts"
    __table_args__ = (
        UniqueConstraint("company_id", "account_code"),
        Index("ix_financial_accounts_company_id", "company_id"),
        Index(
            "ix_financial_accounts_company_id_financial_account_type_code",
            "company_id",
            "financial_account_type_code",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    account_code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    financial_account_type_code: Mapped[str] = mapped_column(String(30), nullable=False)
    gl_account_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    bank_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bank_account_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bank_branch: Mapped[str | None] = mapped_column(String(120), nullable=True)
    currency_code: Mapped[str] = mapped_column(
        String(3),
        ForeignKey("currencies.code", ondelete="RESTRICT"),
        nullable=False,
    )

    company: Mapped["Company"] = relationship("Company")
    gl_account: Mapped["Account"] = relationship("Account")
    currency: Mapped["Currency"] = relationship("Currency")
