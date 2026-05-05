"""Repository for the materialized stock-ledger balance cache.

Balance rows are keyed by ``(company_id, item_id, location_id)`` with the
sentinel value ``0`` substituted for ``None`` locations so the composite PK
remains simple and portable across SQLite / Firebird / PostgreSQL.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.inventory.models.stock_ledger_balance import StockLedgerBalance


_NO_LOCATION_SENTINEL = 0


def _normalize_location(location_id: int | None) -> int:
    return _NO_LOCATION_SENTINEL if location_id is None else int(location_id)


class StockLedgerBalanceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Locking access (used by the writer)
    # ------------------------------------------------------------------

    def get_for_update(
        self,
        company_id: int,
        item_id: int,
        location_id: int | None,
    ) -> StockLedgerBalance | None:
        """Return the balance row with a row-level lock if supported.

        Backends that do not support ``SELECT ... FOR UPDATE`` (e.g. SQLite)
        silently no-op; the caller still gets the freshest committed view.
        """
        loc = _normalize_location(location_id)
        stmt = (
            select(StockLedgerBalance)
            .where(
                StockLedgerBalance.company_id == company_id,
                StockLedgerBalance.item_id == item_id,
                StockLedgerBalance.location_id == loc,
            )
            .with_for_update()
        )
        return self._session.scalars(stmt).first()

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get(
        self,
        company_id: int,
        item_id: int,
        location_id: int | None,
    ) -> StockLedgerBalance | None:
        loc = _normalize_location(location_id)
        stmt = select(StockLedgerBalance).where(
            StockLedgerBalance.company_id == company_id,
            StockLedgerBalance.item_id == item_id,
            StockLedgerBalance.location_id == loc,
        )
        return self._session.scalars(stmt).first()

    def list_for_company(self, company_id: int) -> list[StockLedgerBalance]:
        stmt = (
            select(StockLedgerBalance)
            .where(StockLedgerBalance.company_id == company_id)
            .order_by(StockLedgerBalance.item_id, StockLedgerBalance.location_id)
        )
        return list(self._session.scalars(stmt))

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def upsert(
        self,
        company_id: int,
        item_id: int,
        location_id: int | None,
        quantity: Decimal,
        value: Decimal,
        avg_cost: Decimal,
        last_movement_id: int | None,
    ) -> StockLedgerBalance:
        existing = self.get(company_id, item_id, location_id)
        if existing is None:
            entity = StockLedgerBalance(
                company_id=company_id,
                item_id=item_id,
                location_id=_normalize_location(location_id),
                quantity=quantity,
                value=value,
                avg_cost=avg_cost,
                last_movement_id=last_movement_id,
                version=1,
            )
            self._session.add(entity)
            return entity
        existing.quantity = quantity
        existing.value = value
        existing.avg_cost = avg_cost
        existing.last_movement_id = last_movement_id
        existing.version = (existing.version or 0) + 1
        self._session.add(existing)
        return existing
