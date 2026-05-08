from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from seeker_accounting.modules.payroll.models.payroll_run_employee import PayrollRunEmployee


class PayrollRun(TimestampMixin, Base):
    """A payroll processing run for a specific company pay period.

    status_code values (enforced in service):
        draft          – created, not yet calculated
        calculated     – engines have run, employee rows exist, pending approval
        approved       – approved for posting, cannot be recalculated
        posted         – posted to GL; immutable for accounting-sensitive changes
        reversed       – previously posted run that has been offset in the GL
                         by a reversal journal entry; settlement records remain
                         visible but no further accounting changes occur on
                         this run.
        voided         – cancelled, cannot be used

    One regular run per (company_id, period_year, period_month), plus optional
    off-cycle runs sequenced separately.
    Once posted, settlement tracking (payments, remittances) may still proceed.
    """

    __tablename__ = "payroll_runs"
    __table_args__ = (
        UniqueConstraint("company_id", "run_reference"),
        UniqueConstraint(
            "company_id",
            "period_year",
            "period_month",
            "run_type_code",
            "run_sequence",
            name="uq_payroll_runs_company_id_period_year_period_month_run_type_code_run_sequence",
        ),
        Index("ix_payroll_runs_company_id", "company_id"),
        Index("ix_payroll_runs_company_period", "company_id", "period_year", "period_month"),
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
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    submitted_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    sent_back_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    sent_back_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    sent_back_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    approved_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    posted_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    posted_journal_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("journal_entries.id", ondelete="RESTRICT"),
        nullable=True,
    )
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    reversed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    reversal_journal_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("journal_entries.id", ondelete="RESTRICT"),
        nullable=True,
    )
    reversal_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    run_type_code: Mapped[str] = mapped_column(String(20), nullable=False, default="regular")
    run_sequence: Mapped[int] = mapped_column(Integer(), nullable=False, default=1)
    off_cycle_reason_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    off_cycle_employee_ids: Mapped[str | None] = mapped_column(Text(), nullable=True)
    source_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("payroll_runs.id", ondelete="SET NULL"),
        nullable=True,
    )

    employees: Mapped[list[PayrollRunEmployee]] = relationship(
        "PayrollRunEmployee",
        back_populates="run",
        cascade="all, delete-orphan",
    )
