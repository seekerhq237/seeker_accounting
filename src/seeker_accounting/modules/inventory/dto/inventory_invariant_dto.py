"""DTOs for the inventory invariant checker service.

Per ``docs/inventory_upgrade_plan.md`` Slice 8.1: the invariant checker
surfaces discrepancies between the append-only ledger and the materialized
balance cache, and between cost-layer remaining values and ledger values.
Discrepancies land in a "System Health" report — they are never silent.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class LedgerBalanceMismatchDTO:
    """A discrepancy between the ledger sum and the materialized balance row.

    ``ledger_qty`` and ``ledger_value`` are computed by replaying every
    ``StockLedgerEntry`` for the triple; ``balance_qty`` and ``balance_value``
    are read from the ``StockLedgerBalance`` cache.  A healthy system should
    always have ``ledger_qty == balance_qty`` and ``ledger_value == balance_value``.
    """

    company_id: int
    item_id: int
    location_id: int | None
    ledger_qty: Decimal
    ledger_value: Decimal
    balance_qty: Decimal
    balance_value: Decimal
    qty_delta: Decimal       # ledger_qty  - balance_qty  (non-zero → mismatch)
    value_delta: Decimal     # ledger_value - balance_value (non-zero → mismatch)


@dataclass(frozen=True, slots=True)
class LayerValueMismatchDTO:
    """A discrepancy between cost-layer remaining value and the ledger value.

    ``layer_value`` is the sum of ``quantity_remaining * unit_cost`` across all
    open cost layers for the triple; ``ledger_value`` is read from the
    ``StockLedgerBalance`` cache.  In a healthy weighted-average or FIFO system
    these should be equal within the configured rounding tolerance.
    """

    company_id: int
    item_id: int
    location_id: int | None
    layer_value: Decimal
    ledger_value: Decimal
    delta: Decimal           # layer_value - ledger_value (non-zero → mismatch)


@dataclass(frozen=True, slots=True)
class InventoryInvariantReportDTO:
    """Aggregated result of a full invariant check for one company."""

    company_id: int
    ledger_balance_mismatches: list[LedgerBalanceMismatchDTO]
    layer_value_mismatches: list[LayerValueMismatchDTO]

    @property
    def is_clean(self) -> bool:
        """True when every invariant holds — no discrepancies found."""
        return not self.ledger_balance_mismatches and not self.layer_value_mismatches

    @property
    def total_issues(self) -> int:
        return len(self.ledger_balance_mismatches) + len(self.layer_value_mismatches)
