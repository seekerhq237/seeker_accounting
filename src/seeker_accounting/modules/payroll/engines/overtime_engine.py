"""Overtime Engine — Cameroon multi-tier overtime.

Computes overtime pay for each overtime component assigned to the employee.

Cameroon overtime structure (Code du Travail Art. 80):
  OVERTIME_DAY_T1  — first 8 hrs/week  : 120 % (20 % premium)
  OVERTIME_DAY_T2  — next 8 hrs/week   : 130 % (30 % premium)
  OVERTIME_DAY_T3  — next 4 hrs/week   : 140 % (40 % premium)  [max 20 hrs/wk]
  OVERTIME_NIGHT   — night hours        : 150 % (50 % premium)

Each tier has its own component and rule set.  The user enters hours per tier
as input_quantity on the corresponding component.  The engine reads the premium
rate from the tier's rule set (stored as percentage points, e.g. 20.00 for 20 %)
and computes: hourly_rate × hours × (1 + premium/100).

The legacy generic OVERTIME component with OVERTIME_STANDARD rule set is still
supported for backward compatibility (single multiplier mode).
"""

from __future__ import annotations

from decimal import Decimal

from seeker_accounting.modules.payroll.engines.engine_types import (
    EngineContext,
    EngineLineResult,
)

_STANDARD_HOURS_PER_MONTH = Decimal("173.33")  # ILO standard approximation

# Map component code → rule set code
_OT_RULE_MAP: dict[str, str] = {
    "OVERTIME": "OVERTIME_STANDARD",
    "OVERTIME_DAY_T1": "OVERTIME_DAY_T1",
    "OVERTIME_DAY_T2": "OVERTIME_DAY_T2",
    "OVERTIME_DAY_T3": "OVERTIME_DAY_T3",
    "OVERTIME_NIGHT": "OVERTIME_NIGHT",
}

_OT_CODES = frozenset(_OT_RULE_MAP.keys())


def run_overtime_engine(ctx: EngineContext) -> list[EngineLineResult]:
    """Produce overtime earning lines for all overtime components."""
    results: list[EngineLineResult] = []

    for comp in ctx.components:
        if comp.component_code not in _OT_CODES:
            continue

        if comp.input_amount is not None:
            # Direct amount provided — use it (manual override)
            results.append(
                EngineLineResult(
                    component_id=comp.component_id,
                    component_type_code="earning",
                    calculation_basis=comp.input_amount,
                    rate_applied=None,
                    component_amount=comp.input_amount.quantize(Decimal("0.0001")),
                )
            )
        elif comp.input_quantity is not None and comp.input_quantity > 0:
            # Hours provided — compute: hourly_rate × hours × multiplier
            hourly_rate = ctx.basic_salary / _STANDARD_HOURS_PER_MONTH
            premium_rate = _resolve_premium_rate(comp.component_code, ctx)
            multiplier = Decimal("1") + premium_rate
            ot_amount = (hourly_rate * comp.input_quantity * multiplier).quantize(Decimal("0.0001"))
            results.append(
                EngineLineResult(
                    component_id=comp.component_id,
                    component_type_code="earning",
                    calculation_basis=hourly_rate * comp.input_quantity,
                    rate_applied=multiplier,
                    component_amount=ot_amount,
                )
            )

    return results


def _resolve_premium_rate(component_code: str, ctx: EngineContext) -> Decimal:
    """Resolve overtime premium rate from the component's rule set.

    Returns the premium as a decimal fraction (e.g. 0.20 for 20 % premium).
    Falls back to 0.50 (50 % = 150 %) if no rule set found.
    """
    rule_code = _OT_RULE_MAP.get(component_code)
    if rule_code:
        rule_set = ctx.rule_sets.get(rule_code)
        if rule_set and rule_set.brackets:
            bracket = rule_set.brackets[0]
            if bracket.rate > 0:
                return bracket.rate  # Already decimal (e.g. 0.20 for 20 %)

    # Fallback: 50 % premium (legacy OVERTIME_STANDARD behaviour)
    return Decimal("0.50")
