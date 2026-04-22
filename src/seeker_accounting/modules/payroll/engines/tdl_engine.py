"""TDL Engine (Taxe de Développement Local — Cameroon local development tax).

Computes the TDL using the TDL_MAIN step-bracket rule set.

TDL base = gross_earnings (all earnings, before other deductions).
TDL is a step-bracket levy: the salary falls into exactly one bracket,
and that bracket's fixed amount is the tax due.

Default fallback: no TDL if no rule set or TDL component configured.
"""

from __future__ import annotations

from decimal import Decimal

from seeker_accounting.modules.payroll.engines.engine_types import (
    EngineContext,
    EngineLineResult,
    RuleSetInput,
)

_TDL_RULE = "TDL_MAIN"


def run_tdl_engine(
    ctx: EngineContext,
    tdl_base: Decimal,
) -> list[EngineLineResult]:
    """Produce the TDL deduction line."""
    results: list[EngineLineResult] = []

    tdl_comp = _find_component(ctx, "TDL")
    if tdl_comp is None:
        return results

    # Guard: TDL on zero or negative base produces zero
    if tdl_base <= Decimal("0"):
        return results

    rule_set = ctx.rule_sets.get(_TDL_RULE)
    amount = _resolve_tdl_bracket(tdl_base, rule_set)

    if amount == Decimal("0"):
        return results

    results.append(
        EngineLineResult(
            component_id=tdl_comp.component_id,
            component_type_code="tax",
            calculation_basis=tdl_base,
            rate_applied=None,
            component_amount=amount,
        )
    )

    return results


def _find_component(ctx: EngineContext, code: str):
    for comp in ctx.components:
        if comp.component_code == code:
            return comp
    return None


def _resolve_tdl_bracket(base: Decimal, rule_set: RuleSetInput | None) -> Decimal:
    """Find the TDL fixed amount from the bracket whose range covers the gross salary.

    TDL is a step-bracket levy — the salary matches exactly one bracket,
    and that bracket's fixed_amount is the entire tax due.
    """
    if rule_set is None or not rule_set.brackets:
        return Decimal("0")

    matched_amount = Decimal("0")
    for bracket in rule_set.brackets:
        if base <= bracket.lower_bound:
            break
        if bracket.upper_bound is None or base < bracket.upper_bound:
            matched_amount = bracket.fixed_amount
            break
        matched_amount = bracket.fixed_amount
    return matched_amount.quantize(Decimal("0.0001"))
