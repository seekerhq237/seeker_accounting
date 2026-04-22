from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, utcnow


class BankStatementLine(Base):
    __tablename__ = "bank_statement_lines"
    __table_args__ = (
        Index("ix_bank_statement_lines_company_id", "company_id"),
        Index(
            "ix_bank_statement_lines_company_id_financial_account_id",
            "company_id",
            "financial_account_id",
        ),
        Index(
            "ix_bank_statement_lines_company_id_is_reconciled",
            "company_id",
            "is_reconciled",
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
    import_batch_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("bank_statement_import_batches.id", ondelete="RESTRICT"),
        nullable=True,
    )
    line_date: Mapped[date] = mapped_column(Date(), nullable=False)
    value_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    debit_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0.00"))
    credit_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0.00"))
    is_reconciled: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)

    company: Mapped["Company"] = relationship("Company")
    financial_account: Mapped["FinancialAccount"] = relationship("FinancialAccount")
    import_batch: Mapped["BankStatementImportBatch | None"] = relationship(
        "BankStatementImportBatch", back_populates="lines"
    )
