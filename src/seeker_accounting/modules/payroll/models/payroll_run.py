from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class PayrollRun(TimestampMixin, Base):
    """A payroll processing run for a specific company pay period.

    status_code values (enforced in service):
        draft          – created, not yet calculated
        calculated     – engines have run, employee rows exist, pending approval
        approved       – approved for posting, cannot be recalculated
        posted         – posted to GL; immutable for accounting-sensitive changes
        voided         – cancelled, cannot be used

    One non-voided run per (company_id, period_year, period_month).
    Once posted, settlement tracking (payments, remittances) may still proceed.
    """

    __tablename__ = "payroll_runs"
    __table_args__ = (
        UniqueConstraint("company_id", "run_reference"),
        UniqueConstraint("company_id", "period_year", "period_month"),
        Index("ix_payroll_runs_company_id", "company_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    run_reference: Mapped[str] = mapped_column(String(30), nullable=False)
    run_label: Mapped[str] = mapped_column(String(100), nullable=False)
    period_year: Mapped[int] = mapped_column(Integer(), nullable=False)
    period_month: Mapped[int] = mapped_column(Integer(), nullable=False)
    status_code: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    currency_code: Mapped[str] = mapped_column(
        String(3),
        ForeignKey("currencies.code", ondelete="RESTRICT"),
        nullable=False,
    )
    run_date: Mapped[date] = mapped_column(Date(), nullable=False)
    payment_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    calculated_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    posted_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    posted_journal_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("journal_entries.id", ondelete="RESTRICT"),
        nullable=True,
    )

    employees: Mapped[list["PayrollRunEmployee"]] = relationship(
        "PayrollRunEmployee",
        back_populates="run",
        cascade="all, delete-orphan",
    )
