"""Inventory ABC Analysis Service — Pareto analysis on COGS consumption.

Ranks items by total COGS consumed in a period, then classifies:
  A = top 80 % of cumulative COGS
  B = next 15 %
  C = remaining 5 %
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.inventory.models.stock_ledger_entry import StockLedgerEntry
from seeker_accounting.platform.exceptions import ValidationError

_ZERO = Decimal("0")


@dataclass
class AbcItemDTO:
    item_id: int
    item_code: str
    item_name: str
    total_cogs: Decimal
    pct_of_total: Decimal
    cumulative_pct: Decimal
    abc_class: str      # "A" | "B" | "C"


@dataclass
class InventoryAbcReportDTO:
    company_id: int
    date_from: date
    date_to: date
    total_cogs: Decimal
    rows: list[AbcItemDTO]


# Cumulative boundaries for A/B
_A_BOUNDARY = Decimal("80")
_B_BOUNDARY = Decimal("95")


class InventoryAbcAnalysisService:
    def __init__(self, unit_of_work_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = unit_of_work_factory

    def get_report(
        self, company_id: int, date_from: date, date_to: date
    ) -> InventoryAbcReportDTO:
        if date_from > date_to:
            raise ValidationError("date_from must be on or before date_to.")

        with self._uow_factory() as uow:
            return self._build(uow.session, company_id, date_from, date_to)

    def _build(
        self, session: Session, company_id: int, date_from: date, date_to: date
    ) -> InventoryAbcReportDTO:
        from seeker_accounting.modules.inventory.models.item import Item

        # COGS = stock issues (direction=-1) valued at unit_cost
        stmt = (
            select(
                StockLedgerEntry.item_id,
                func.sum(
                    StockLedgerEntry.quantity_base * StockLedgerEntry.unit_cost
                ).label("total_cogs"),
            )
            .where(
                StockLedgerEntry.company_id == company_id,
                StockLedgerEntry.direction == -1,
                StockLedgerEntry.posting_date >= date_from,
                StockLedgerEntry.posting_date <= date_to,
            )
            .group_by(StockLedgerEntry.item_id)
            .order_by(func.sum(StockLedgerEntry.quantity_base * StockLedgerEntry.unit_cost).desc())
        )

        items_map = {
            row.id: (row.item_code, row.item_name)
            for row in session.scalars(select(Item).where(Item.company_id == company_id))
        }

        raw = [(r.item_id, Decimal(str(r.total_cogs or 0))) for r in session.execute(stmt)]
        total = sum(v for _, v in raw) or _ZERO

        rows: list[AbcItemDTO] = []
        cumulative = _ZERO
        for item_id, cogs in raw:
            pct = (cogs / total * 100).quantize(Decimal("0.01")) if total else _ZERO
            cumulative += pct
            if cumulative <= _A_BOUNDARY:
                abc = "A"
            elif cumulative <= _B_BOUNDARY:
                abc = "B"
            else:
                abc = "C"
            code, name = items_map.get(item_id, ("", ""))
            rows.append(
                AbcItemDTO(
                    item_id=item_id,
                    item_code=code,
                    item_name=name,
                    total_cogs=cogs,
                    pct_of_total=pct,
                    cumulative_pct=cumulative,
                    abc_class=abc,
                )
            )

        return InventoryAbcReportDTO(
            company_id=company_id,
            date_from=date_from,
            date_to=date_to,
            total_cogs=total,
            rows=rows,
        )
