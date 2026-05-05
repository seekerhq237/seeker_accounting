"""Stock reservation repository.

Manages ``StockReservation`` persistence. Business-state transitions
(pending → fulfilled, cancelled, expired) are owned by
``StockReservationService``; this repository owns only data access.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.inventory.models.stock_reservation import StockReservation

_PENDING = "pending"


class StockReservationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, reservation: StockReservation) -> None:
        self._session.add(reservation)

    def get(self, reservation_id: int, company_id: int) -> StockReservation | None:
        return self._session.scalar(
            select(StockReservation).where(
                StockReservation.id == reservation_id,
                StockReservation.company_id == company_id,
            )
        )

    def list_pending_for_item_location(
        self,
        company_id: int,
        item_id: int,
        location_id: int | None,
    ) -> list[StockReservation]:
        stmt = select(StockReservation).where(
            StockReservation.company_id == company_id,
            StockReservation.item_id == item_id,
            StockReservation.status_code == _PENDING,
        )
        if location_id is not None:
            stmt = stmt.where(StockReservation.location_id == location_id)
        else:
            stmt = stmt.where(StockReservation.location_id.is_(None))
        return list(self._session.scalars(stmt))

    def list_by_source(
        self,
        company_id: int,
        source_module: str,
        source_document_id: int,
    ) -> list[StockReservation]:
        stmt = select(StockReservation).where(
            StockReservation.company_id == company_id,
            StockReservation.source_module == source_module,
            StockReservation.source_document_id == source_document_id,
        )
        return list(self._session.scalars(stmt))

    def total_reserved_quantity(
        self,
        company_id: int,
        item_id: int,
        location_id: int | None,
    ) -> Decimal:
        stmt = select(func.coalesce(func.sum(StockReservation.quantity), 0)).where(
            StockReservation.company_id == company_id,
            StockReservation.item_id == item_id,
            StockReservation.status_code == _PENDING,
        )
        if location_id is not None:
            stmt = stmt.where(StockReservation.location_id == location_id)
        else:
            stmt = stmt.where(StockReservation.location_id.is_(None))
        result = self._session.scalar(stmt)
        return Decimal(str(result)) if result is not None else Decimal("0.0000")

    def expire_stale(self, company_id: int, as_of: datetime) -> int:
        """Expire all pending reservations whose ``expires_at`` has passed.

        Returns the number of rows updated.
        """
        rows = self._session.scalars(
            select(StockReservation).where(
                StockReservation.company_id == company_id,
                StockReservation.status_code == _PENDING,
                StockReservation.expires_at <= as_of,
            )
        ).all()
        for r in rows:
            r.status_code = "expired"
        return len(rows)
