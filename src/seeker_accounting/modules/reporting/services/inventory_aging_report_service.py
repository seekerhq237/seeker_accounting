"""Inventory Ageing Report Service — cost layers by age bucket.

Analyses the stock-on-hand by when it was received, sliced into buckets:
  0–30 days, 31–60, 61–90, 91–180, 180+ days old.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.inventory.models.stock_ledger_balance import StockLedgerBalance
from seeker_accounting.modules.inventory.models.stock_ledger_entry import StockLedgerEntry

_ZERO = Decimal("0")
_BUCKETS = [(0, 30), (31, 60), (61, 90), (91, 180), (181, None)]
_BUCKET_LABELS = ["0-30 days", "31-60 days", "61-90 days", "91-180 days", "180+ days"]


@dataclass
class AgeingItemRowDTO:
    item_id: int
    item_code: str
    item_name: str
    on_hand_qty: Decimal
    on_hand_value: Decimal
    bucket_values: list[Decimal]   # one per bucket, matching _BUCKET_LABELS


@dataclass
class InventoryAgeingReportDTO:
    as_of_date: date
    company_id: int
    bucket_labels: list[str]
    rows: list[AgeingItemRowDTO]
    total_value: Decimal
    bucket_totals: list[Decimal]


class InventoryAgeingReportService:
    def __init__(self, unit_of_work_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = unit_of_work_factory

    def get_report(self, company_id: int, as_of_date: date | None = None) -> InventoryAgeingReportDTO:
        today = as_of_date or date.today()

        with self._uow_factory() as uow:
            return self._build(uow.session, company_id, today)

    def _build(self, session: Session, company_id: int, today: date) -> InventoryAgeingReportDTO:
        from seeker_accounting.modules.inventory.models.item import Item

        items_map = {
            row.id: (row.item_code, row.item_name)
            for row in session.scalars(
                select(Item).where(Item.company_id == company_id)
            )
        }

        balances = list(
            session.scalars(
                select(StockLedgerBalance).where(
                    StockLedgerBalance.company_id == company_id,
                    StockLedgerBalance.quantity > 0,
                )
            )
        )

        rows: list[AgeingItemRowDTO] = []
        bucket_totals = [_ZERO] * len(_BUCKET_LABELS)
        total_value = _ZERO

        for bal in balances:
            bucket_values = self._spread_to_buckets(session, company_id, bal, today)
            code, name = items_map.get(bal.item_id, ("", ""))
            row_total = sum(bucket_values)
            rows.append(
                AgeingItemRowDTO(
                    item_id=bal.item_id,
                    item_code=code,
                    item_name=name,
                    on_hand_qty=Decimal(str(bal.quantity)),
                    on_hand_value=Decimal(str(bal.value)),
                    bucket_values=bucket_values,
                )
            )
            for i, v in enumerate(bucket_values):
                bucket_totals[i] += v
            total_value += Decimal(str(bal.value))

        return InventoryAgeingReportDTO(
            as_of_date=today,
            company_id=company_id,
            bucket_labels=_BUCKET_LABELS[:],
            rows=rows,
            total_value=total_value,
            bucket_totals=bucket_totals,
        )

    def _spread_to_buckets(
        self, session: Session, company_id: int, bal: StockLedgerBalance, today: date
    ) -> list[Decimal]:
        """Approximation: query receipt entries and assign to buckets by their age."""
        stmt = (
            select(StockLedgerEntry)
            .where(
                StockLedgerEntry.company_id == company_id,
                StockLedgerEntry.item_id == bal.item_id,
                StockLedgerEntry.location_id == (bal.location_id or None),
                StockLedgerEntry.direction == 1,
            )
            .order_by(StockLedgerEntry.posting_date.desc())
        )
        entries = list(session.scalars(stmt))

        bucket_values = [_ZERO] * len(_BUCKET_LABELS)
        remaining = Decimal(str(bal.quantity))

        for e in entries:
            if remaining <= _ZERO:
                break
            age_days = (today - e.posting_date).days if e.posting_date else 999
            take = min(remaining, Decimal(str(e.quantity_base)))
            bucket_idx = self._bucket_index(age_days)
            bucket_values[bucket_idx] += take * Decimal(str(e.unit_cost))
            remaining -= take

        return bucket_values

    @staticmethod
    def _bucket_index(age_days: int) -> int:
        for i, (lo, hi) in enumerate(_BUCKETS):
            if hi is None or age_days <= hi:
                return i
        return len(_BUCKETS) - 1
