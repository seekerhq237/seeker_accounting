"""StockLedgerService — the **single allowed writer** to the stock ledger.

Per ``docs/inventory_upgrade_plan.md`` Slice 2.1: stock truth lives in an
immutable, append-only ledger. Every business workflow that moves stock
(inventory document posting, future sales-invoice cost-of-goods-sold,
production receipts/issues, transfers) must call
:meth:`StockLedgerService.append` exactly once per stock-moving line.

Direction sign convention:

* ``+1`` — stock IN (receipts, transfers in, customer returns, positive
  adjustments, count gains).
* ``-1`` — stock OUT (issues, transfers out, supplier returns, negative
  adjustments, scrap, wastage, count losses).

Costing semantics (weighted average, mirroring the legacy cost-layer engine):

* On a **receipt**: ``unit_cost`` from the caller is used to compute the value
  delta; the new running ``avg_cost`` is recomputed from total value over
  total quantity.
* On an **issue**: the ledger consumes at the **current running average
  cost** — the caller's ``unit_cost`` is informational only. The avg cost
  stays unchanged after an issue (canonical weighted-average semantics).

Concurrency: the writer takes a row-level lock on the
``stock_ledger_balances`` row for the affected ``(company, item, location)``
triple via ``SELECT ... FOR UPDATE``. SQLite is a no-op (single-writer) but
PostgreSQL / Firebird honour the lock.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.modules.inventory.models.stock_ledger_entry import StockLedgerEntry
from seeker_accounting.modules.inventory.repositories.stock_ledger_balance_repository import (
    StockLedgerBalanceRepository,
)
from seeker_accounting.modules.inventory.repositories.stock_ledger_entry_repository import (
    StockLedgerEntryRepository,
)
from seeker_accounting.platform.exceptions import ValidationError
from seeker_accounting.platform.numerics.rounding_policy import (
    quantize_amount,
    quantize_internal_cost,
    quantize_quantity,
)


StockLedgerEntryRepositoryFactory = Callable[[Session], StockLedgerEntryRepository]
StockLedgerBalanceRepositoryFactory = Callable[[Session], StockLedgerBalanceRepository]


_ZERO_QTY = Decimal("0.0000")
_ZERO_AMOUNT = Decimal("0.00")
_ZERO_COST = Decimal("0.000000")


class StockLedgerService:
    def __init__(
        self,
        entry_repository_factory: StockLedgerEntryRepositoryFactory,
        balance_repository_factory: StockLedgerBalanceRepositoryFactory,
    ) -> None:
        self._entry_repository_factory = entry_repository_factory
        self._balance_repository_factory = balance_repository_factory

    # ------------------------------------------------------------------
    # Public API — single writer
    # ------------------------------------------------------------------

    def append(
        self,
        session: Session,
        *,
        company_id: int,
        item_id: int,
        location_id: int | None,
        posting_date: date,
        document_type_code: str,
        inventory_document_line_id: int | None,
        direction: int,
        quantity_base: Decimal,
        unit_cost: Decimal,
        batch_id: int | None = None,
    ) -> StockLedgerEntry:
        """Append a stock movement and update the materialized balance.

        Raises :class:`ValidationError` for invalid direction, non-positive
        quantity, or insufficient on-hand on a stock-out movement.
        """
        if direction not in (1, -1):
            raise ValidationError(
                f"Stock ledger direction must be +1 or -1, got {direction}."
            )

        qty_delta = quantize_quantity(quantity_base)
        if qty_delta <= _ZERO_QTY:
            raise ValidationError(
                "Stock ledger quantity must be strictly positive; "
                "use ``direction`` to encode stock-in / stock-out."
            )

        balance_repo = self._balance_repository_factory(session)
        entry_repo = self._entry_repository_factory(session)

        balance = balance_repo.get_for_update(company_id, item_id, location_id)
        if balance is None:
            old_qty = _ZERO_QTY
            old_value = _ZERO_AMOUNT
            old_avg = _ZERO_COST
        else:
            old_qty = Decimal(balance.quantity)
            old_value = Decimal(balance.value)
            old_avg = Decimal(balance.avg_cost)

        if direction == 1:
            effective_unit_cost = quantize_internal_cost(unit_cost)
            value_delta = quantize_amount(qty_delta * effective_unit_cost)
            new_qty = quantize_quantity(old_qty + qty_delta)
            new_value = quantize_amount(old_value + value_delta)
            new_avg = (
                quantize_internal_cost(new_value / new_qty)
                if new_qty > _ZERO_QTY
                else _ZERO_COST
            )
        else:
            if qty_delta > old_qty:
                raise ValidationError(
                    f"Insufficient on-hand for item {item_id} at location "
                    f"{location_id if location_id is not None else 'unset'}: "
                    f"available {old_qty}, requested {qty_delta}."
                )
            # Issues consume at the running weighted-average cost. The
            # caller's ``unit_cost`` is informational only; we ignore it for
            # the value delta to preserve weighted-average invariants.
            effective_unit_cost = old_avg
            value_delta = quantize_amount(qty_delta * effective_unit_cost)
            new_qty = quantize_quantity(old_qty - qty_delta)
            new_value = quantize_amount(old_value - value_delta)
            # Avg cost is preserved across issues; collapse to zero only if
            # the position is fully drained.
            new_avg = old_avg if new_qty > _ZERO_QTY else _ZERO_COST

        entry = StockLedgerEntry(
            company_id=company_id,
            item_id=item_id,
            location_id=location_id,
            posting_date=posting_date,
            document_type_code=document_type_code,
            inventory_document_line_id=inventory_document_line_id,
            batch_id=batch_id,
            direction=direction,
            quantity_base=qty_delta,
            unit_cost=effective_unit_cost,
            value=value_delta,
            running_quantity_after=new_qty,
            running_value_after=new_value,
            running_avg_cost_after=new_avg,
        )
        entry_repo.add(entry)
        session.flush()

        balance_repo.upsert(
            company_id=company_id,
            item_id=item_id,
            location_id=location_id,
            quantity=new_qty,
            value=new_value,
            avg_cost=new_avg,
            last_movement_id=entry.id,
        )
        return entry
