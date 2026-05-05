"""Stock impairment provisions (P5 / Slice 6.3 — OHADA Class 39).

Captures year-end or interim provisions for obsolete / slow-moving stock.
Posting creates:  Dr Expense (6594 or similar)  Cr Provision (391x/392x/393x)

status_code choices: 'draft', 'posted', 'reversed'
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    pass


class StockImpairmentProvision(TimestampMixin, Base):
    """A single impairment provision entry for one item/location."""

    __tablename__ = "stock_impairment_provisions"
    __table_args__ = (
        Index("ix_stock_impairment_company_item", "company_id", "item_id"),
        Index("ix_stock_impairment_period", "company_id", "fiscal_period_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False
    )
    item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("items.id", ondelete="RESTRICT"), nullable=False
    )
    location_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("inventory_locations.id", ondelete="RESTRICT"), nullable=True
    )
    fiscal_period_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("fiscal_periods.id", ondelete="RESTRICT"), nullable=False
    )
    provision_account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    expense_account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    provision_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    status_code: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    journal_entry_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("journal_entries.id", ondelete="RESTRICT"), nullable=True
    )
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    posted_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
