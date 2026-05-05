"""Repository for PriceList and PriceListLine (P6 / Slice 7.1)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.inventory.models.price_list import PriceList, PriceListLine


class PriceListRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Price list headers
    # ------------------------------------------------------------------

    def get(self, price_list_id: int) -> PriceList | None:
        return self._session.get(PriceList, price_list_id)

    def get_default(self, company_id: int) -> PriceList | None:
        stmt = select(PriceList).where(
            PriceList.company_id == company_id,
            PriceList.is_default.is_(True),
            PriceList.is_active.is_(True),
        )
        return self._session.scalars(stmt).first()

    def list_active(self, company_id: int) -> Sequence[PriceList]:
        stmt = (
            select(PriceList)
            .where(PriceList.company_id == company_id, PriceList.is_active.is_(True))
            .order_by(PriceList.name)
        )
        return self._session.scalars(stmt).all()

    def list_all(self, company_id: int) -> Sequence[PriceList]:
        stmt = (
            select(PriceList)
            .where(PriceList.company_id == company_id)
            .order_by(PriceList.name)
        )
        return self._session.scalars(stmt).all()

    def add(self, price_list: PriceList) -> None:
        self._session.add(price_list)

    def delete(self, price_list: PriceList) -> None:
        self._session.delete(price_list)

    # ------------------------------------------------------------------
    # Price list lines
    # ------------------------------------------------------------------

    def get_line(self, line_id: int) -> PriceListLine | None:
        return self._session.get(PriceListLine, line_id)

    def list_lines_for_item(
        self, company_id: int, item_id: int, as_of_date: date | None = None
    ) -> Sequence[PriceListLine]:
        """Returns all active price list lines for an item, optionally filtered by date."""
        stmt = (
            select(PriceListLine)
            .join(PriceList, PriceList.id == PriceListLine.price_list_id)
            .where(
                PriceList.company_id == company_id,
                PriceList.is_active.is_(True),
                PriceListLine.item_id == item_id,
            )
        )
        if as_of_date:
            stmt = stmt.where(
                (PriceListLine.valid_from.is_(None)) | (PriceListLine.valid_from <= as_of_date),
                (PriceListLine.valid_to.is_(None)) | (PriceListLine.valid_to >= as_of_date),
            )
        return self._session.scalars(stmt).all()

    def add_line(self, line: PriceListLine) -> None:
        self._session.add(line)

    def delete_line(self, line: PriceListLine) -> None:
        self._session.delete(line)
