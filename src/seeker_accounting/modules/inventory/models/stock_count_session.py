from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class StockCountSession(TimestampMixin, Base):
    """Frozen execution instance of a stock count plan."""

    __tablename__ = "stock_count_sessions"
    __table_args__ = (
        Index("ix_stock_count_sessions_company_status", "company_id", "status_code"),
        Index("ix_stock_count_sessions_plan_id", "plan_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False
    )
    plan_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stock_count_plans.id", ondelete="RESTRICT"), nullable=False
    )
    session_number: Mapped[str] = mapped_column(String(40), nullable=False)
    session_date: Mapped[date] = mapped_column(Date(), nullable=False)
    status_code: Mapped[str] = mapped_column(
        String(30), nullable=False, default="planning", server_default="planning"
    )
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    frozen_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    approved_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    posted_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    company: Mapped["Company"] = relationship("Company")
    plan: Mapped["StockCountPlan"] = relationship("StockCountPlan", back_populates="sessions")
    frozen_by_user: Mapped["User | None"] = relationship("User", foreign_keys=[frozen_by_user_id])
    approved_by_user: Mapped["User | None"] = relationship("User", foreign_keys=[approved_by_user_id])
    posted_by_user: Mapped["User | None"] = relationship("User", foreign_keys=[posted_by_user_id])
    lines: Mapped[list["StockCountLine"]] = relationship(
        "StockCountLine", back_populates="session", cascade="all, delete-orphan"
    )
