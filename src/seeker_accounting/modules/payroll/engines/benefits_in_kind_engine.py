"""Benefits-in-Kind Engine.

Handles components flagged as benefits-in-kind (BIK), such as housing
allowance when provided in-kind, company vehicles, etc.

BIK components are identified by component_code membership in _BIK_CODES.

BIK amounts:
  - Count toward gross_earnings
  - Count toward taxable_salary_base (they are taxable, unless flagged otherwise)
  - Do NOT count toward cnps_contributory_base unless is_pensionable is set
  - Do NOT result in a cash payment to the employee (informational for tax)

Statutory rate resolution (H1 fix):
  The engine first attempts to read the rate from the BIK-specific rule set
  (e.g., HOUSING_BIK_MAIN = 15 %) seeded from Arrêté N° 039/CAB/MINFI.
  Only if no rule set exists does it fall back to the component's base_rate.
  A manual input_amount override always wins over computed rate.
"""

from __future__ import annotations

from decimal import Decimal

from seeker_accounting.modules.payroll.engines.engine_types import (
    EngineContext,
    EngineLineResult,
    quantize_xaf,
)

_BIK_CODES = frozenset({
    "HOUSING_BIK", "ELECTRICITY_BIK", "WATER_BIK", "DOMESTIC_BIK",
    "MEAL_BIK", "VEHICLE_BIK", "VEHICLE_BIK_2", "TRANSPORT_BIK",
})

# Map BIK component code → authoritative rule set code (from statutory pack)
_BIK_RULE_MAP: dict[str, str] = {
    "HOUSING_BIK":    "HOUSING_BIK_MAIN",
    "ELECTRICITY_BIK": "ELECTRICITY_BIK_MAIN",
    "WATER_BIK":      "WATER_BIK_MAIN",
    "DOMESTIC_BIK":   "DOMESTIC_BIK_MAIN",
    "MEAL_BIK":       "MEAL_BIK_MAIN",
    "VEHICLE_BIK":    "VEHICLE_BIK_MAIN",
    "VEHICLE_BIK_2":  "VEHICLE_BIK_2_MAIN",
}


def run_benefits_in_kind_engine(ctx: EngineContext) -> list[EngineLineResult]:
    """Produce earning lines for benefits-in-kind components."""
    results: list[EngineLineResult] = []

    for comp in ctx.components:
        if comp.component_code not in _BIK_CODES:
            continue
        if comp.component_type_code != "earning":
            continue

        amount = _resolve_bik_amount(comp, ctx)
        if amount == Decimal("0"):
            continue

        results.append(
            EngineLineResult(
                component_id=comp.component_id,
                component_type_code="earning",
                calculation_basis=ctx.basic_salary,
                rate_applied=_effective_rate(comp, ctx),
                component_amount=amount,
            )
        )

    return results


def _effective_rate(comp, ctx: EngineContext) -> Decimal | None:
    """Return the rate actually used (for audit trail on the line result)."""
    rule_code = _BIK_RULE_MAP.get(comp.component_code)
    if rule_code:
        rs = ctx.rule_sets.get(rule_code)
        if rs and rs.brackets and rs.brackets[0].rate > 0:
            return rs.brackets[0].rate
    return comp.base_rate if comp.base_rate > 0 else None


def _resolve_bik_amount(comp, ctx: EngineContext) -> Decimal:
    # Manual input amount always wins
    if comp.input_amount is not None:
        return quantize_xaf(comp.input_amount)

    # Try authoritative statutory rate from pack rule set first
    rule_code = _BIK_RULE_MAP.get(comp.component_code)
    if rule_code:
        rs = ctx.rule_sets.get(rule_code)
        if rs and rs.brackets and rs.brackets[0].rate > 0:
            return quantize_xaf(ctx.basic_salary * rs.brackets[0].rate)

    # Fall back to component-level configuration
    if comp.calculation_method_code == "fixed_amount":
        return quantize_xaf(comp.base_amount)
    if comp.calculation_method_code == "percentage" and comp.base_rate > 0:
        return quantize_xaf(ctx.basic_salary * comp.base_rate)

    return Decimal("0")
