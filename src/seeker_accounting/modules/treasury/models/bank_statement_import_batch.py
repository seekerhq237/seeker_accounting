from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, utcnow


class BankStatementImportBatch(Base):
    __tablename__ = "bank_statement_import_batches"
    __table_args__ = (
        Index("ix_bank_statement_import_batches_company_id", "company_id"),
        Index(
            "ix_bank_statement_import_batches_company_id_financial_account_id",
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
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    import_source: Mapped[str] = mapped_column(String(30), nullable=False)
    statement_start_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    statement_end_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    line_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)
    imported_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )

    company: Mapped["Company"] = relationship("Company")
    financial_account: Mapped["FinancialAccount"] = relationship("FinancialAccount")
    imported_by_user: Mapped["User | None"] = relationship("User", foreign_keys=[imported_by_user_id])
    lines: Mapped[list["BankStatementLine"]] = relationship(
        "BankStatementLine",
        back_populates="import_batch",
    )
