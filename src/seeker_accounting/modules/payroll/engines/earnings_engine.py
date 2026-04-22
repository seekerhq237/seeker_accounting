"""Earnings Engine.

Computes base salary, fixed allowances (housing, transport, etc.), and any
fixed-amount or manual-input earning components that are not overtime or BIK.

Returns earning lines for use in gross_earnings accumulation.
"""

from __future__ import annotations

from decimal import Decimal

from seeker_accounting.modules.payroll.engines.engine_types import (
    EngineContext,
    EngineLineResult,
)

_EARNING_METHODS = frozenset({"fixed_amount", "manual_input", "percentage"})
# Codes handled by their own engines — skip them here
_DELEGATED_CODES = frozenset({
    "OVERTIME", "OVERTIME_DAY_T1", "OVERTIME_DAY_T2", "OVERTIME_DAY_T3", "OVERTIME_NIGHT",
    "HOUSING_BIK", "TRANSPORT_BIK",
})


def run_earnings_engine(ctx: EngineContext) -> list[EngineLineResult]:
    """Produce earning lines for all non-overtime, non-BIK earning components."""
    results: list[EngineLineResult] = []

    for comp in ctx.components:
        if comp.component_type_code != "earning":
            continue
        # Overtime and benefits-in-kind handled by their own engines
        if comp.component_code in _DELEGATED_CODES:
            continue

        amount = _resolve_amount(comp, ctx.basic_salary)
        if amount == Decimal("0") and comp.calculation_method_code != "manual_input":
            continue

        results.append(
            EngineLineResult(
                component_id=comp.component_id,
                component_type_code="earning",
                calculation_basis=ctx.basic_salary,
                rate_applied=comp.base_rate if comp.calculation_method_code == "percentage" else None,
                component_amount=amount,
            )
        )

    return results


def _resolve_amount(comp, basic_salary: Decimal) -> Decimal:
    # Variable input overrides everything when provided
    if comp.input_amount is not None:
        return comp.input_amount.quantize(Decimal("0.0001"))

    if comp.calculation_method_code == "fixed_amount":
        return comp.base_amount.quantize(Decimal("0.0001"))

    if comp.calculation_method_code == "percentage":
        return (basic_salary * comp.base_rate).quantize(Decimal("0.0001"))

    if comp.calculation_method_code == "manual_input":
        # No input provided — skip
        return Decimal("0")

    return Decimal("0")
