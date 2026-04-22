"""Employer Contribution Engine.

Computes employer-side contributions:
  - FNE Patronale (Fonds National de l'Emploi) — 2.5 % of gross salary via FNE_EMPLOYER_MAIN
  - Family Allowances (CNPS PF) — configurable rate via AF_MAIN rule set
  - Accident Risk — percentage per ACCIDENT_RISK_STANDARD rule set
  - Any other employer_contribution components

These do not reduce employee net pay but increase the employer's total cost.
"""

from __future__ import annotations

from decimal import Decimal

from seeker_accounting.modules.payroll.engines.engine_types import (
    EngineContext,
    EngineLineResult,
    RuleSetInput,
)

_ACCIDENT_RISK_RULE = "ACCIDENT_RISK_STANDARD"
_AF_RULE = "AF_MAIN"
_FNE_EMPLOYER_RULE = "FNE_EMPLOYER_MAIN"

# PROVISIONAL FALLBACK — Cameroon 2024 rates.
# Used only when the corresponding rule set is not configured.
_DEFAULT_ACCIDENT_RATE = Decimal("0.0175")  # 1.75 % — Group A
_DEFAULT_FNE_EMPLOYER_RATE = Decimal("0.025")  # 2.5 % — Cameroon 2024 (barème-verified)
_DEFAULT_AF_RATE = Decimal("0.07")  # 7 % — General regime


def run_employer_contribution_engine(
    ctx: EngineContext,
    gross_earnings: Decimal,
) -> list[EngineLineResult]:
    """Produce employer contribution lines."""
    results: list[EngineLineResult] = []

    # Guard: no employer contributions on zero or negative gross
    if gross_earnings <= Decimal("0"):
        return results

    for comp in ctx.components:
        if comp.component_type_code != "employer_contribution":
            continue
        # CNPS employer is handled by the CNPS engine
        if comp.component_code == "EMPLOYER_CNPS":
            continue

        amount = _resolve_contribution_amount(comp, ctx, gross_earnings)
        if amount == Decimal("0"):
            continue

        results.append(
            EngineLineResult(
                component_id=comp.component_id,
                component_type_code="employer_contribution",
                calculation_basis=gross_earnings,
                rate_applied=comp.base_rate if comp.base_rate > 0 else None,
                component_amount=amount,
            )
        )

    return results


def _resolve_contribution_amount(comp, ctx: EngineContext, gross_earnings: Decimal) -> Decimal:
    # Manual input override
    if comp.input_amount is not None:
        return comp.input_amount.quantize(Decimal("0.0001"))

    if comp.component_code == "ACCIDENT_RISK_EMPLOYER":
        return _calculate_accident_risk(gross_earnings, ctx.rule_sets.get(_ACCIDENT_RISK_RULE))

    if comp.component_code == "FNE":
        return _calculate_rate_from_rule(
            gross_earnings, ctx.rule_sets.get(_FNE_EMPLOYER_RULE), _DEFAULT_FNE_EMPLOYER_RATE
        )

    if comp.component_code == "EMPLOYER_AF":
        return _calculate_rate_from_rule(
            gross_earnings, ctx.rule_sets.get(_AF_RULE), _DEFAULT_AF_RATE
        )

    if comp.calculation_method_code == "fixed_amount":
        return comp.base_amount.quantize(Decimal("0.0001"))

    if comp.calculation_method_code == "percentage":
        rate = comp.base_rate if comp.base_rate > 0 else Decimal("0")
        return (gross_earnings * rate).quantize(Decimal("0.0001"))

    # Generic rule_based: try base_rate if set
    if comp.calculation_method_code == "rule_based" and comp.base_rate > 0:
        return (gross_earnings * comp.base_rate).quantize(Decimal("0.0001"))

    return Decimal("0")


def _calculate_rate_from_rule(
    gross: Decimal, rule_set: RuleSetInput | None, default_rate: Decimal
) -> Decimal:
    """Apply a rate from the first bracket of a rule set, with cap support."""
    if gross <= Decimal("0"):
        return Decimal("0")
    if rule_set and rule_set.brackets:
        bracket = rule_set.brackets[0]
        rate = bracket.rate if bracket.rate > 0 else default_rate
        amount = (gross * rate).quantize(Decimal("0.0001"))
        if bracket.cap_amount and bracket.cap_amount > 0:
            amount = min(amount, bracket.cap_amount)
        return max(amount, Decimal("0"))
    return max((gross * default_rate).quantize(Decimal("0.0001")), Decimal("0"))


def _calculate_accident_risk(gross: Decimal, rule_set: RuleSetInput | None) -> Decimal:
    if gross <= Decimal("0"):
        return Decimal("0")
    if rule_set and rule_set.brackets:
        bracket = rule_set.brackets[0]
        rate = bracket.rate if bracket.rate > 0 else _DEFAULT_ACCIDENT_RATE
        # Respect cap from bracket if present
        amount = (gross * rate).quantize(Decimal("0.0001"))
        if bracket.cap_amount and bracket.cap_amount > 0:
            amount = min(amount, bracket.cap_amount)
        return max(amount, Decimal("0"))
    else:
        rate = _DEFAULT_ACCIDENT_RATE
    return max((gross * rate).quantize(Decimal("0.0001")), Decimal("0"))
