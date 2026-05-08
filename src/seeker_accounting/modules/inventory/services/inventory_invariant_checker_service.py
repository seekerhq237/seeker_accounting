"""InventoryInvariantCheckerService — on-demand consistency checker.

Per ``docs/inventory_upgrade_plan.md`` Slice 8.1: for every
``(company_id, item_id, location_id)`` triple the following invariants must
hold:

1. ``sum(ledger.direction * ledger.quantity_base) == balances.quantity``
2. ``sum(ledger.direction * ledger.value) == balances.value``
3. ``sum(layer.quantity_remaining * layer.unit_cost) == balances.value``
   (within rounding tolerance — the cost-layer engine and the ledger writer
   apply the same quantization, but minor diffs can appear with FIFO if the
   source data is inconsistent)

Discrepancies are returned as typed DTOs for surfacing on a "System Health"
page; nothing is silently swallowed.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.inventory.dto.inventory_invariant_dto import (
    InventoryInvariantReportDTO,
    LayerValueMismatchDTO,
    LedgerBalanceMismatchDTO,
)
from seeker_accounting.modules.inventory.models.inventory_cost_layer import InventoryCostLayer
from seeker_accounting.modules.inventory.models.stock_ledger_balance import StockLedgerBalance
from seeker_accounting.modules.inventory.models.stock_ledger_entry import StockLedgerEntry

UnitOfWorkFactoryType = UnitOfWorkFactory


_ZERO = Decimal("0")
# Rounding tolerance for cost-layer vs ledger value comparison.
# One cent is the minimum representable rounding unit in the system.
_VALUE_TOLERANCE = Decimal("0.01")


class InventoryInvariantCheckerService:
    """On-demand checker that verifies ledger ↔ balance and layer ↔ ledger invariants."""

    def __init__(self, unit_of_work_factory: UnitOfWorkFactoryType) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(self, company_id: int) -> InventoryInvariantReportDTO:
        """Run all invariant checks for *company_id* and return a full report.

        This is a read-only operation; it never mutates any row.
        """
        with self._unit_of_work_factory() as uow:
            session = uow.session
            assert session is not None
            ledger_mismatches = self._check_ledger_vs_balances(session, company_id)
            layer_mismatches = self._check_layer_vs_ledger(session, company_id)

        return InventoryInvariantReportDTO(
            company_id=company_id,
            ledger_balance_mismatches=ledger_mismatches,
            layer_value_mismatches=layer_mismatches,
        )

    # ------------------------------------------------------------------
    # Invariant 1 + 2: ledger sums == materialized balance
    # ------------------------------------------------------------------

    def _check_ledger_vs_balances(
        self, session: Session, company_id: int
    ) -> list[LedgerBalanceMismatchDTO]:
        """Verify sum(direction * qty) == balance.quantity for every triple."""

        # Aggregate ledger: sum qty and value per (item, location).
        # The sentinel location_id=0 in balance rows corresponds to NULL in ledger rows;
        # the balance repo uses 0 as a sentinel — we keep the comparison consistent
        # by using the ledger's natural NULL grouping here and mapping at comparison time.
        agg_stmt = (
            select(
                StockLedgerEntry.item_id,
                StockLedgerEntry.location_id,
                func.sum(
                    StockLedgerEntry.direction * StockLedgerEntry.quantity_base
                ).label("total_qty"),
                func.sum(
                    StockLedgerEntry.direction * StockLedgerEntry.value
                ).label("total_value"),
            )
            .where(StockLedgerEntry.company_id == company_id)
            .group_by(StockLedgerEntry.item_id, StockLedgerEntry.location_id)
        )
        ledger_rows = session.execute(agg_stmt).all()

        # Build lookup dict keyed by (item_id, location_id_or_none).
        ledger_map: dict[tuple[int, int | None], tuple[Decimal, Decimal]] = {}
        for row in ledger_rows:
            qty = Decimal(str(row.total_qty)) if row.total_qty is not None else _ZERO
            val = Decimal(str(row.total_value)) if row.total_value is not None else _ZERO
            ledger_map[(row.item_id, row.location_id)] = (qty, val)

        # Fetch all balance rows for this company.
        balance_rows = list(
            session.scalars(
                select(StockLedgerBalance).where(
                    StockLedgerBalance.company_id == company_id
                )
            )
        )

        _SENTINEL = 0  # maps to location_id=None in the ledger
        mismatches: list[LedgerBalanceMismatchDTO] = []

        # Check every balance row against the ledger aggregate.
        seen_triples: set[tuple[int, int | None]] = set()
        for bal in balance_rows:
            loc_null = None if bal.location_id == _SENTINEL else bal.location_id
            triple_key = (bal.item_id, loc_null)
            seen_triples.add(triple_key)

            ledger_qty, ledger_val = ledger_map.get(triple_key, (_ZERO, _ZERO))
            balance_qty = Decimal(str(bal.quantity))
            balance_val = Decimal(str(bal.value))
            qty_delta = ledger_qty - balance_qty
            val_delta = ledger_val - balance_val

            if qty_delta != _ZERO or val_delta != _ZERO:
                mismatches.append(
                    LedgerBalanceMismatchDTO(
                        company_id=company_id,
                        item_id=bal.item_id,
                        location_id=loc_null,
                        ledger_qty=ledger_qty,
                        ledger_value=ledger_val,
                        balance_qty=balance_qty,
                        balance_value=balance_val,
                        qty_delta=qty_delta,
                        value_delta=val_delta,
                    )
                )

        # Also flag ledger triples with no balance row (orphan entries).
        for (item_id, loc_null), (ledger_qty, ledger_val) in ledger_map.items():
            if (item_id, loc_null) in seen_triples:
                continue
            if ledger_qty != _ZERO or ledger_val != _ZERO:
                mismatches.append(
                    LedgerBalanceMismatchDTO(
                        company_id=company_id,
                        item_id=item_id,
                        location_id=loc_null,
                        ledger_qty=ledger_qty,
                        ledger_value=ledger_val,
                        balance_qty=_ZERO,
                        balance_value=_ZERO,
                        qty_delta=ledger_qty,
                        value_delta=ledger_val,
                    )
                )

        return mismatches

    # ------------------------------------------------------------------
    # Invariant 3: cost-layer remaining value == ledger value
    # ------------------------------------------------------------------

    def _check_layer_vs_ledger(
        self, session: Session, company_id: int
    ) -> list[LayerValueMismatchDTO]:
        """Verify sum(layer.remaining * unit_cost) == balance.value for every triple."""

        # Aggregate cost layers: sum remaining value per (item, location).
        layer_agg_stmt = (
            select(
                InventoryCostLayer.item_id,
                InventoryCostLayer.location_id,
                func.sum(
                    InventoryCostLayer.quantity_remaining * InventoryCostLayer.unit_cost
                ).label("layer_value"),
            )
            .where(InventoryCostLayer.company_id == company_id)
            .group_by(InventoryCostLayer.item_id, InventoryCostLayer.location_id)
        )
        layer_rows = session.execute(layer_agg_stmt).all()

        layer_map: dict[tuple[int, int | None], Decimal] = {}
        for row in layer_rows:
            val = Decimal(str(row.layer_value)) if row.layer_value is not None else _ZERO
            layer_map[(row.item_id, row.location_id)] = val

        # Fetch all balance rows.
        balance_rows = list(
            session.scalars(
                select(StockLedgerBalance).where(
                    StockLedgerBalance.company_id == company_id
                )
            )
        )

        _SENTINEL = 0
        mismatches: list[LayerValueMismatchDTO] = []

        for bal in balance_rows:
            loc_null = None if bal.location_id == _SENTINEL else bal.location_id
            layer_val = layer_map.get((bal.item_id, loc_null), _ZERO)
            ledger_val = Decimal(str(bal.value))
            delta = layer_val - ledger_val

            # Only flag when cost layers are in use for this triple.
            # If layer_val is zero and ledger_val is non-zero, it means the
            # posting path (e.g. a direct ledger write without cost layers) has
            # not written any layer rows — this is a valid posting mode for
            # weighted-average entries written via StockLedgerService alone.
            if layer_val == _ZERO:
                continue

            if abs(delta) > _VALUE_TOLERANCE:
                mismatches.append(
                    LayerValueMismatchDTO(
                        company_id=company_id,
                        item_id=bal.item_id,
                        location_id=loc_null,
                        layer_value=layer_val,
                        ledger_value=ledger_val,
                        delta=delta,
                    )
                )

        return mismatches
