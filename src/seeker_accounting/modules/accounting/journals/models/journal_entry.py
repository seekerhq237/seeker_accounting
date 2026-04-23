from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class JournalEntry(TimestampMixin, Base):
    __tablename__ = "journal_entries"
    __table_args__ = (
        UniqueConstraint("company_id", "entry_number"),
        Index("ix_journal_entries_company_id_entry_date", "company_id", "entry_date"),
        Index("ix_journal_entries_company_id_status_code", "company_id", "status_code"),
        # Source-document reverse lookup: jump from an operational document
        # (invoice, transfer, payroll run, etc.) back to its posted journal
        # entry without scanning the whole journal table.
        Index(
            "ix_journal_entries_source_document",
            "source_module_code",
            "source_document_type",
            "source_document_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    fiscal_period_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("fiscal_periods.id", ondelete="RESTRICT"),
        nullable=False,
    )
    entry_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    entry_date: Mapped[date] = mapped_column(Date(), nullable=False)
    transaction_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    journal_type_code: Mapped[str] = mapped_column(String(30), nullable=False)
    reference_text: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_module_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_document_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_document_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status_code: Mapped[str] = mapped_column(String(20), nullable=False)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    posted_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )

    company: Mapped["Company"] = relationship("Company")
    fiscal_period: Mapped["FiscalPeriod"] = relationship("FiscalPeriod", back_populates="journal_entries")
    posted_by_user: Mapped["User | None"] = relationship("User", foreign_keys=[posted_by_user_id])
    created_by_user: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_user_id])
    lines: Mapped[list["JournalEntryLine"]] = relationship(
        "JournalEntryLine",
        back_populates="journal_entry",
    )
