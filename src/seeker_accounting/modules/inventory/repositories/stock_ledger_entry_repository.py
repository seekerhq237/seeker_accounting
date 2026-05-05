"""Repository for the immutable stock ledger entries table."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.inventory.models.stock_ledger_entry import StockLedgerEntry


class StockLedgerEntryRepository:
    """Read / append-only access to ``stock_ledger_entries``.

    The ledger is append-only by contract — there is intentionally no
    ``update`` or ``delete`` method. Mutations to a posted stock movement
    must go through a reversing entry.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def add(self, entity: StockLedgerEntry) -> StockLedgerEntry:
        self._session.add(entity)
        return entity

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def last_for_item_location(
        self,
        company_id: int,
        item_id: int,
        location_id: int | None,
    ) -> StockLedgerEntry | None:
        """Return the most recent entry for the (item, location) triple."""
        stmt = (
            select(StockLedgerEntry)
            .where(
                StockLedgerEntry.company_id == company_id,
                StockLedgerEntry.item_id == item_id,
            )
            .order_by(StockLedgerEntry.posting_date.desc(), StockLedgerEntry.id.desc())
            .limit(1)
        )
        if location_id is None:
            stmt = stmt.where(StockLedgerEntry.location_id.is_(None))
        else:
            stmt = stmt.where(StockLedgerEntry.location_id == location_id)
        return self._session.scalars(stmt).first()

    def list_until(
        self,
        company_id: int,
        item_id: int,
        location_id: int | None,
        as_of: date,
    ) -> list[StockLedgerEntry]:
        """Return every entry up to and including ``as_of`` in chronological order."""
        stmt = (
            select(StockLedgerEntry)
            .where(
                StockLedgerEntry.company_id == company_id,
                StockLedgerEntry.item_id == item_id,
                StockLedgerEntry.posting_date <= as_of,
            )
            .order_by(StockLedgerEntry.posting_date, StockLedgerEntry.id)
        )
        if location_id is None:
            stmt = stmt.where(StockLedgerEntry.location_id.is_(None))
        else:
            stmt = stmt.where(StockLedgerEntry.location_id == location_id)
        return list(self._session.scalars(stmt))
