"""StockLedgerQueryService — read-side queries on the stock ledger.

Position queries return:

* **Current** — read straight from the ``stock_ledger_balances`` cache.
* **As-of** — replay every ledger entry up to the cut-off date, in
  chronological order, to derive the historical position. The replay is
  authoritative; the cache is only an optimisation for the current state.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.inventory.dto.stock_ledger_dto import StockLedgerPositionDTO
from seeker_accounting.modules.inventory.repositories.stock_ledger_balance_repository import (
    StockLedgerBalanceRepository,
)
from seeker_accounting.modules.inventory.repositories.stock_ledger_entry_repository import (
    StockLedgerEntryRepository,
)


StockLedgerEntryRepositoryFactory = Callable[[Session], StockLedgerEntryRepository]
StockLedgerBalanceRepositoryFactory = Callable[[Session], StockLedgerBalanceRepository]


_ZERO_QTY = Decimal("0.0000")
_ZERO_AMOUNT = Decimal("0.00")
_ZERO_COST = Decimal("0.000000")


class StockLedgerQueryService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        entry_repository_factory: StockLedgerEntryRepositoryFactory,
        balance_repository_factory: StockLedgerBalanceRepositoryFactory,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._entry_repository_factory = entry_repository_factory
        self._balance_repository_factory = balance_repository_factory

    def position(
        self,
        company_id: int,
        item_id: int,
        location_id: int | None,
        as_of: date | None = None,
    ) -> StockLedgerPositionDTO:
        with self._unit_of_work_factory() as uow:
            session = uow.session
            assert session is not None
            if as_of is None:
                balance = self._balance_repository_factory(session).get(
                    company_id, item_id, location_id
                )
                if balance is None:
                    return StockLedgerPositionDTO(
                        company_id=company_id,
                        item_id=item_id,
                        location_id=location_id,
                        on_hand=_ZERO_QTY,
                        value=_ZERO_AMOUNT,
                        avg_cost=_ZERO_COST,
                    )
                return StockLedgerPositionDTO(
                    company_id=company_id,
                    item_id=item_id,
                    location_id=location_id,
                    on_hand=Decimal(balance.quantity),
                    value=Decimal(balance.value),
                    avg_cost=Decimal(balance.avg_cost),
                )

            # As-of replay: take the running totals from the most recent
            # entry whose posting_date <= as_of.
            entries = self._entry_repository_factory(session).list_until(
                company_id, item_id, location_id, as_of
            )
            if not entries:
                return StockLedgerPositionDTO(
                    company_id=company_id,
                    item_id=item_id,
                    location_id=location_id,
                    on_hand=_ZERO_QTY,
                    value=_ZERO_AMOUNT,
                    avg_cost=_ZERO_COST,
                )
            last = entries[-1]
            return StockLedgerPositionDTO(
                company_id=company_id,
                item_id=item_id,
                location_id=location_id,
                on_hand=Decimal(last.running_quantity_after),
                value=Decimal(last.running_value_after),
                avg_cost=Decimal(last.running_avg_cost_after),
            )
