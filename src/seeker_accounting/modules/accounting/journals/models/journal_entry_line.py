from __future__ import annotations

from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class JournalEntryLine(TimestampMixin, Base):
    __tablename__ = "journal_entry_lines"
    __table_args__ = (
        CheckConstraint("debit_amount >= 0", name="debit_amount_non_negative"),
        CheckConstraint("credit_amount >= 0", name="credit_amount_non_negative"),
        UniqueConstraint("journal_entry_id", "line_number"),
        Index("ix_journal_entry_lines_project_id", "project_id"),
        Index("ix_journal_entry_lines_project_job_id", "project_job_id"),
        Index("ix_journal_entry_lines_project_cost_code_id", "project_cost_code_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    journal_entry_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("journal_entries.id", ondelete="RESTRICT"),
        nullable=False,
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    account_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    line_description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    debit_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    credit_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    contract_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("contracts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    project_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=True,
    )
    project_job_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("project_jobs.id", ondelete="RESTRICT"),
        nullable=True,
    )
    project_cost_code_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("project_cost_codes.id", ondelete="RESTRICT"),
        nullable=True,
    )

    journal_entry: Mapped["JournalEntry"] = relationship("JournalEntry", back_populates="lines")
    account: Mapped["Account"] = relationship("Account")
    contract: Mapped["Contract | None"] = relationship("Contract")
    project: Mapped["Project | None"] = relationship("Project")
    project_job: Mapped["ProjectJob | None"] = relationship("ProjectJob")
    project_cost_code: Mapped["ProjectCostCode | None"] = relationship("ProjectCostCode")
