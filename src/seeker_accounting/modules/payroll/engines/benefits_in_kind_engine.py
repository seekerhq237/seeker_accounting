"""Benefits-in-Kind Engine.

Handles components flagged as benefits-in-kind (BIK), such as housing
allowance when provided in-kind, company vehicles, etc.

BIK components are identified by component_code containing "BIK" or by
having component_type_code == "earning" and a specific naming convention.

BIK amounts:
  - Count toward gross_earnings
  - Count toward taxable_salary_base (they are taxable)
  - Do NOT count toward cnps_contributory_base unless is_pensionable is set
  - Do NOT result in a cash payment to the employee (informational for tax)

In this implementation, BIK amounts are still counted as earnings for
simplicity, with the taxability flag controlling IRPP base inclusion.
"""

from __future__ import annotations

from decimal import Decimal

from seeker_accounting.modules.payroll.engines.engine_types import (
    EngineContext,
    EngineLineResult,
)

_BIK_CODES = frozenset({"HOUSING_BIK", "TRANSPORT_BIK", "VEHICLE_BIK", "MEAL_BIK"})


def run_benefits_in_kind_engine(ctx: EngineContext) -> list[EngineLineResult]:
    """Produce earning lines for benefits-in-kind components."""
    results: list[EngineLineResult] = []

    for comp in ctx.components:
        if comp.component_code not in _BIK_CODES:
            continue
        if comp.component_type_code != "earning":
            continue

        amount = _resolve_bik_amount(comp, ctx.basic_salary)
        if amount == Decimal("0"):
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


def _resolve_bik_amount(comp, basic_salary: Decimal) -> Decimal:
    if comp.input_amount is not None:
        return comp.input_amount.quantize(Decimal("0.0001"))
    if comp.calculation_method_code == "fixed_amount":
        return comp.base_amount.quantize(Decimal("0.0001"))
    if comp.calculation_method_code == "percentage":
        return (basic_salary * comp.base_rate).quantize(Decimal("0.0001"))
    return Decimal("0")
