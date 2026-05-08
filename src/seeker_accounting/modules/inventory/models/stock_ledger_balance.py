"""Materialized stock-ledger position cache.

One row per ``(company_id, item_id, location_id)`` triple. Always equals the
running totals of the most recent ``StockLedgerEntry`` for that triple, by
construction (``StockLedgerService.append`` updates both atomically under a
row-level lock).

The ``version`` column supports optimistic-concurrency checks for callers that
need them; the ledger writer uses pessimistic ``SELECT ... FOR UPDATE`` (the
balance row is the lock target for parallel posting attempts on the same item
and location).
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Numeric, PrimaryKeyConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class StockLedgerBalance(TimestampMixin, Base):
    """Current per-(company, item, location) stock position."""

    __tablename__ = "stock_ledger_balances"
    __table_args__ = (
        PrimaryKeyConstraint(
            "company_id",
            "item_id",
            "location_id",
            name="pk_stock_ledger_balances",
        ),
        Index("ix_stock_ledger_balances_company_id", "company_id"),
        Index("ix_stock_ledger_balances_item_id", "item_id"),
        CheckConstraint("quantity >= 0", name="ck_slb_quantity_nonneg"),
    )

    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    item_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # location_id is part of the PK; SQLite/Firebird/Postgres all permit a
    # zero-sentinel location for "no location" legacy rows. We use ``0`` as
    # the sentinel so the PK can be a simple composite without nullable
    # columns (multi-row NULLs would defeat the PK on most backends).
    location_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    avg_cost: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0")
    )
    last_movement_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("stock_ledger_entries.id", ondelete="RESTRICT"),
        nullable=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    company: Mapped["Company"] = relationship("Company")
    item: Mapped["Item"] = relationship("Item")
    last_movement: Mapped["StockLedgerEntry | None"] = relationship("StockLedgerEntry")
