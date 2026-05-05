"""Rounding policy used by every inventory, sales, purchase, and treasury posting.

Per CLAUDE.md and the Phase 0 inventory upgrade plan:

* Decimal arithmetic is performed in full precision; quantization happens **only**
  when writing a value to a persisted ``*_amount`` column or producing a final
  report value.
* Quantities are stored to 4 decimals on persisted columns.
* Unit costs are stored to 4 decimals on persisted columns; intermediate
  computations may use higher precision (6 decimals) before final quantization.
* Monetary amounts are stored to 2 decimals.
* All quantization uses ``ROUND_HALF_EVEN`` (banker's rounding) to avoid the
  systematic bias of ``ROUND_HALF_UP`` over large posting volumes.

The legacy ``shared/utils/money.py`` ``quantize_money`` helper continues to use
``ROUND_HALF_UP`` to remain backwards-compatible with already-posted accounting
data; new code paths in inventory, COGS, GRN, and stock-ledger postings use the
helpers in this module instead.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_EVEN
from typing import Final


QUANTITY_PRECISION: Final[Decimal] = Decimal("0.0001")
"""Quantization template for persisted base-quantity values (4 decimals)."""

UNIT_COST_PRECISION: Final[Decimal] = Decimal("0.0001")
"""Quantization template for persisted unit-cost values (4 decimals)."""

INTERNAL_COST_PRECISION: Final[Decimal] = Decimal("0.000001")
"""Quantization template for intermediate cost computations (6 decimals)."""

AMOUNT_PRECISION: Final[Decimal] = Decimal("0.01")
"""Quantization template for persisted monetary amounts (2 decimals)."""


def _coerce(value: Decimal | float | int | str) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def quantize_quantity(value: Decimal | float | int | str) -> Decimal:
    """Quantize a quantity to ``QUANTITY_PRECISION`` with banker's rounding."""

    return _coerce(value).quantize(QUANTITY_PRECISION, rounding=ROUND_HALF_EVEN)


def quantize_unit_cost(value: Decimal | float | int | str) -> Decimal:
    """Quantize a unit cost to ``UNIT_COST_PRECISION`` with banker's rounding."""

    return _coerce(value).quantize(UNIT_COST_PRECISION, rounding=ROUND_HALF_EVEN)


def quantize_internal_cost(value: Decimal | float | int | str) -> Decimal:
    """Quantize an intermediate cost to ``INTERNAL_COST_PRECISION``.

    Use this for chained cost computations (avg cost, FIFO consumption, landed
    cost allocation, etc.) **before** the final ``quantize_unit_cost`` /
    ``quantize_amount`` step that writes to a persisted column.
    """

    return _coerce(value).quantize(INTERNAL_COST_PRECISION, rounding=ROUND_HALF_EVEN)


def quantize_amount(value: Decimal | float | int | str) -> Decimal:
    """Quantize a monetary amount to ``AMOUNT_PRECISION`` with banker's rounding."""

    return _coerce(value).quantize(AMOUNT_PRECISION, rounding=ROUND_HALF_EVEN)
