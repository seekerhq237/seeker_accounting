"""Deferral schedule models.

A deferral schedule tracks a prepaid expense (charges constatées d'avance)
or unearned revenue (produits constatés d'avance) over a set recognition period.

OHADA accounts:
  - 476  Charges constatées d'avance   (prepaid expense holding)
  - 477  Produits constatés d'avance   (unearned revenue holding)

A DeferralSchedule owns a set of DeferralScheduleLines (one per recognition
period). Each line records the amount to recognise and links to the posted
JournalEntry once the recognition is posted.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin

# ── Status codes ──────────────────────────────────────────────────────
DEFERRAL_STATUS_DRAFT = "DRAFT"
DEFERRAL_STATUS_ACTIVE = "ACTIVE"
DEFERRAL_STATUS_COMPLETE = "COMPLETE"
DEFERRAL_STATUS_CANCELLED = "CANCELLED"

# ── Deferral types ────────────────────────────────────────────────────
DEFERRAL_TYPE_EXPENSE = "EXPENSE"   # prepaid expense → charge constatée d'avance
DEFERRAL_TYPE_REVENUE = "REVENUE"   # unearned revenue → produit constaté d'avance

# ── Recognition line status codes ────────────────────────────────────
LINE_STATUS_PENDING = "PENDING"
LINE_STATUS_POSTED = "POSTED"
LINE_STATUS_SKIPPED = "SKIPPED"


class DeferralSchedule(TimestampMixin, Base):
    """Master record for a deferral schedule.

    One schedule = one prepaid expense or one unearned revenue item
    that is recognised in equal (or customised) instalments over
    ``period_count`` calendar months.
    """

    __tablename__ = "deferral_schedules"
    __table_args__ = (
        CheckConstraint("total_amount > 0", name="deferral_schedule_total_positive"),
        CheckConstraint("period_count > 0", name="deferral_schedule_period_count_positive"),
        Index("ix_deferral_schedules_company_id", "company_id"),
        Index("ix_deferral_schedules_company_id_status", "company_id", "status_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    deferral_type: Mapped[str] = mapped_column(String(10), nullable=False)   # EXPENSE / REVENUE
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    reference_text: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # Accounts
    recognition_account_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
        comment="The P&L account where amounts are recognised (expense or revenue).",
    )
    holding_account_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
        comment="476 (prepaid expense) or 477 (unearned revenue) balance sheet account.",
    )

    # Schedule parameters
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    start_date: Mapped[date] = mapped_column(Date(), nullable=False)
    end_date: Mapped[date] = mapped_column(Date(), nullable=False)
    period_count: Mapped[int] = mapped_column(Integer, nullable=False)

    # Workflow
    status_code: Mapped[str] = mapped_column(String(20), nullable=False, default=DEFERRAL_STATUS_DRAFT)

    # Source document link (optional — invoice, bill, receipt, etc.)
    source_document_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_document_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )

    # Relationships
    lines: Mapped[list["DeferralScheduleLine"]] = relationship(
        "DeferralScheduleLine",
        back_populates="schedule",
        order_by="DeferralScheduleLine.line_number",
        cascade="all, delete-orphan",
    )


class DeferralScheduleLine(TimestampMixin, Base):
    """One recognition instalment on a deferral schedule.

    There is one line per period. On posting the line, ``journal_entry_id``
    is stamped and ``status_code`` advances to POSTED.
    """

    __tablename__ = "deferral_schedule_lines"
    __table_args__ = (
        UniqueConstraint("deferral_schedule_id", "line_number", name="uq_deferral_line_number"),
        CheckConstraint("amount >= 0", name="deferral_line_amount_non_negative"),
        Index("ix_deferral_schedule_lines_schedule_id", "deferral_schedule_id"),
        Index(
            "ix_deferral_schedule_lines_company_pending",
            "deferral_schedule_id",
            "status_code",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    deferral_schedule_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("deferral_schedules.id", ondelete="CASCADE"),
        nullable=False,
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    recognition_date: Mapped[date] = mapped_column(
        Date(),
        nullable=False,
        comment="The accounting date for this recognition JE (typically the last day of the month).",
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    status_code: Mapped[str] = mapped_column(
        String(20), nullable=False, default=LINE_STATUS_PENDING
    )
    journal_entry_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("journal_entries.id", ondelete="RESTRICT"),
        nullable=True,
    )

    # Relationships
    schedule: Mapped["DeferralSchedule"] = relationship(
        "DeferralSchedule", back_populates="lines"
    )
