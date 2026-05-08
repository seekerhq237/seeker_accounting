"""Inventory Kardex Report Service — item ledger card per item/location.

Returns a chronological list of stock ledger entries (the kardex / stock card)
with running balance tracking per item-location.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.inventory.models.stock_ledger_entry import StockLedgerEntry
from seeker_accounting.platform.exceptions import ValidationError

_ZERO = Decimal("0")


@dataclass
class KardexFilterDTO:
    company_id: int
    item_id: int
    location_id: int | None = None
    date_from: date | None = None
    date_to: date | None = None


@dataclass
class KardexLineDTO:
    posting_date: date
    document_type_code: str
    document_number: str | None
    direction: int          # +1 receipt, -1 issue
    quantity: Decimal
    unit_cost: Decimal
    line_value: Decimal
    running_qty: Decimal
    running_value: Decimal
    running_avg_cost: Decimal


@dataclass
class KardexReportDTO:
    item_id: int
    item_code: str
    item_name: str
    location_id: int | None
    location_name: str | None
    date_from: date | None
    date_to: date | None
    opening_qty: Decimal
    opening_value: Decimal
    lines: list[KardexLineDTO]
    closing_qty: Decimal
    closing_value: Decimal


class InventoryKardexReportService:
    def __init__(self, unit_of_work_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = unit_of_work_factory

    def get_report(self, filters: KardexFilterDTO) -> KardexReportDTO:
        if not filters.item_id:
            raise ValidationError("Item is required for the kardex report.")

        with self._uow_factory() as uow:
            return self._build(uow.session, filters)

    # ------------------------------------------------------------------
    def _build(self, session: Session, f: KardexFilterDTO) -> KardexReportDTO:
        from seeker_accounting.modules.inventory.models.item import Item
        from seeker_accounting.modules.inventory.models.inventory_location import InventoryLocation

        item = session.get(Item, f.item_id)
        item_code = item.item_code if item else str(f.item_id)
        item_name = item.item_name if item else ""

        loc_name: str | None = None
        if f.location_id:
            loc = session.get(InventoryLocation, f.location_id)
            loc_name = loc.name if loc else None

        # All entries up to period start for opening balance
        open_stmt = (
            select(StockLedgerEntry)
            .where(
                StockLedgerEntry.company_id == f.company_id,
                StockLedgerEntry.item_id == f.item_id,
                *(
                    [StockLedgerEntry.location_id == f.location_id]
                    if f.location_id is not None
                    else []
                ),
                *(
                    [StockLedgerEntry.posting_date < f.date_from]
                    if f.date_from
                    else []
                ),
            )
            .order_by(StockLedgerEntry.posting_date, StockLedgerEntry.id)
        )
        opening_qty = _ZERO
        opening_value = _ZERO
        for e in session.scalars(open_stmt):
            opening_qty += Decimal(str(e.quantity_base)) * e.direction
            opening_value += Decimal(str(e.quantity_base)) * Decimal(str(e.unit_cost)) * e.direction

        # Entries within period
        period_stmt = (
            select(StockLedgerEntry)
            .where(
                StockLedgerEntry.company_id == f.company_id,
                StockLedgerEntry.item_id == f.item_id,
                *(
                    [StockLedgerEntry.location_id == f.location_id]
                    if f.location_id is not None
                    else []
                ),
                *(
                    [StockLedgerEntry.posting_date >= f.date_from]
                    if f.date_from
                    else []
                ),
                *(
                    [StockLedgerEntry.posting_date <= f.date_to]
                    if f.date_to
                    else []
                ),
            )
            .order_by(StockLedgerEntry.posting_date, StockLedgerEntry.id)
        )

        lines: list[KardexLineDTO] = []
        running_qty = opening_qty
        running_value = opening_value

        for e in session.scalars(period_stmt):
            qty = Decimal(str(e.quantity_base))
            cost = Decimal(str(e.unit_cost))
            val = qty * cost * e.direction
            running_qty += qty * e.direction
            running_value += val
            avg = running_value / running_qty if running_qty else _ZERO
            lines.append(
                KardexLineDTO(
                    posting_date=e.posting_date,
                    document_type_code=e.document_type_code,
                    document_number=None,
                    direction=e.direction,
                    quantity=qty,
                    unit_cost=cost,
                    line_value=val,
                    running_qty=running_qty,
                    running_value=running_value,
                    running_avg_cost=avg,
                )
            )

        return KardexReportDTO(
            item_id=f.item_id,
            item_code=item_code,
            item_name=item_name,
            location_id=f.location_id,
            location_name=loc_name,
            date_from=f.date_from,
            date_to=f.date_to,
            opening_qty=opening_qty,
            opening_value=opening_value,
            lines=lines,
            closing_qty=running_qty,
            closing_value=running_value,
        )
