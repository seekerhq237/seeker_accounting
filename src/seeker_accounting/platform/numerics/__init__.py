"""Numeric and rounding policy primitives shared across business modules."""

from seeker_accounting.platform.numerics.rounding_policy import (
    QUANTITY_PRECISION,
    UNIT_COST_PRECISION,
    AMOUNT_PRECISION,
    INTERNAL_COST_PRECISION,
    quantize_amount,
    quantize_quantity,
    quantize_unit_cost,
    quantize_internal_cost,
)

__all__ = [
    "QUANTITY_PRECISION",
    "UNIT_COST_PRECISION",
    "AMOUNT_PRECISION",
    "INTERNAL_COST_PRECISION",
    "quantize_amount",
    "quantize_quantity",
    "quantize_unit_cost",
    "quantize_internal_cost",
]
