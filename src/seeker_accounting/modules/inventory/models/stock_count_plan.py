from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class StockCountPlan(TimestampMixin, Base):
    """Planned stock count scope before a count session is frozen."""

    __tablename__ = "stock_count_plans"
    __table_args__ = (
        Index("ix_stock_count_plans_company_status", "company_id", "status_code"),
        Index("ix_stock_count_plans_plan_date", "plan_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False
    )
    plan_number: Mapped[str] = mapped_column(String(40), nullable=False)
    plan_date: Mapped[date] = mapped_column(Date(), nullable=False)
    status_code: Mapped[str] = mapped_column(
        String(30), nullable=False, default="planning", server_default="planning"
    )
    cycle_class_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    item_filter_json: Mapped[str | None] = mapped_column(Text(), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )

    company: Mapped["Company"] = relationship("Company")
    created_by_user: Mapped["User | None"] = relationship("User")
    locations: Mapped[list["StockCountPlanLocation"]] = relationship(
        "StockCountPlanLocation", back_populates="plan", cascade="all, delete-orphan"
    )
    sessions: Mapped[list["StockCountSession"]] = relationship("StockCountSession", back_populates="plan")


class StockCountPlanLocation(Base):
    """Location included in a stock count plan."""

    __tablename__ = "stock_count_plan_locations"
    __table_args__ = (Index("ix_stock_count_plan_locations_location_id", "location_id"),)

    plan_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stock_count_plans.id", ondelete="CASCADE"), primary_key=True
    )
    location_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("inventory_locations.id", ondelete="RESTRICT"), primary_key=True
    )

    plan: Mapped["StockCountPlan"] = relationship("StockCountPlan", back_populates="locations")
    location: Mapped["InventoryLocation"] = relationship("InventoryLocation")
