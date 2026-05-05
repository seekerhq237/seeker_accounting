"""Append-only stock ledger entries.

Per ``docs/inventory_upgrade_plan.md`` Slice 2.1: stock truth lives in an
immutable, append-only ledger keyed at ``(company_id, item_id, location_id)``
granularity. Every receipt, issue, and adjustment writes exactly one
``StockLedgerEntry`` per document line. Cost layers, weighted-average
recalculations, and balance positions are derived from this ledger — never
the other way around.

Direction sign convention:

* ``+1`` — stock IN (receipts, transfers in, customer returns, positive
  adjustments, count gains).
* ``-1`` — stock OUT (issues, transfers out, supplier returns, negative
  adjustments, scrap, wastage, count losses).

The ``running_*_after`` columns capture the per-(item, location) running
position **immediately after** this entry was applied, enabling fast as-of
queries and integrity reconciliation against the ``stock_ledger_balances``
materialized cache.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, utcnow


class StockLedgerEntry(Base):
    """Single immutable stock movement fact."""

    __tablename__ = "stock_ledger_entries"
    __table_args__ = (
        Index(
            "ix_stock_ledger_entries_company_item_location_date_id",
            "company_id",
            "item_id",
            "location_id",
            "posting_date",
            "id",
        ),
        Index(
            "ix_stock_ledger_entries_doc_line_id",
            "inventory_document_line_id",
        ),
        Index("ix_stock_ledger_entries_batch_id", "batch_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
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
    location_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("inventory_locations.id", ondelete="RESTRICT"),
        nullable=True,
    )
    posting_date: Mapped[date] = mapped_column(Date(), nullable=False)
    document_type_code: Mapped[str] = mapped_column(String(40), nullable=False)
    inventory_document_line_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("inventory_document_lines.id", ondelete="RESTRICT"),
        nullable=True,
    )
    batch_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("item_batches.id", ondelete="RESTRICT"),
        nullable=True,
    )
    direction: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_base: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    running_quantity_after: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    running_value_after: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    running_avg_cost_after: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)

    company: Mapped["Company"] = relationship("Company")
    item: Mapped["Item"] = relationship("Item")
    location: Mapped["InventoryLocation | None"] = relationship("InventoryLocation")
    inventory_document_line: Mapped["InventoryDocumentLine | None"] = relationship(
        "InventoryDocumentLine"
    )
    batch: Mapped["ItemBatch | None"] = relationship("ItemBatch")
