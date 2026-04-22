from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base


class AssetDepreciationRun(Base):
    """A depreciation run captures a period-end depreciation batch.

    Status lifecycle: draft -> posted | cancelled
    Only draft runs may be edited or cancelled.
    Posted runs are immutable and linked to a journal entry.
    """

    __tablename__ = "asset_depreciation_runs"
    __table_args__ = (
        UniqueConstraint("company_id", "run_number"),
        Index("ix_asset_depreciation_runs_company_id", "company_id"),
        Index("ix_asset_depreciation_runs_company_id_status_code", "company_id", "status_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    run_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    run_date: Mapped[date] = mapped_column(Date(), nullable=False)
    period_end_date: Mapped[date] = mapped_column(Date(), nullable=False)
    status_code: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")

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
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False)

    company: Mapped["Company"] = relationship("Company")
    posted_journal_entry: Mapped["JournalEntry | None"] = relationship(
        "JournalEntry", foreign_keys=[posted_journal_entry_id]
    )
    lines: Mapped[list["AssetDepreciationRunLine"]] = relationship(
        "AssetDepreciationRunLine", back_populates="depreciation_run"
    )
