"""Employer Contribution Engine.

Computes employer-side contributions:
  - FNE Patronale (Fonds National de l'Emploi) — 2.5 % of gross salary via FNE_EMPLOYER_MAIN
  - Family Allowances (CNPS PF) — configurable rate via AF_MAIN rule set
  - Accident Risk — percentage per ACCIDENT_RISK_STANDARD rule set
  - Any other employer_contribution components

These do not reduce employee net pay but increase the employer's total cost.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from seeker_accounting.modules.payroll.engines.engine_types import (
    EngineContext,
    EngineLineResult,
    RuleSetInput,
    quantize_xaf,
)

logger = logging.getLogger(__name__)

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
    cnps_contributory_base: Decimal,
) -> list[EngineLineResult]:
    """Produce employer contribution lines.

    Args:
        ctx: Engine context with components and rule sets.
        gross_earnings: Total gross earnings (used for FNE patronale).
        cnps_contributory_base: Pensionable earnings base (used for AF and Accident Risk
            per Décret N° 2014/2377 — same base as CNPS PVID).
    """
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

        amount = _resolve_contribution_amount(comp, ctx, gross_earnings, cnps_contributory_base)
        if amount == Decimal("0"):
            continue

        # Record the base actually used in calculation_basis for audit trail
        basis = cnps_contributory_base if comp.component_code in ("EMPLOYER_AF", "ACCIDENT_RISK_EMPLOYER") else gross_earnings
        results.append(
            EngineLineResult(
                component_id=comp.component_id,
                component_type_code="employer_contribution",
                calculation_basis=basis,
                rate_applied=comp.base_rate if comp.base_rate > 0 else None,
                component_amount=amount,
            )
        )

    return results


def _resolve_contribution_amount(
    comp,
    ctx: EngineContext,
    gross_earnings: Decimal,
    cnps_contributory_base: Decimal,
) -> Decimal:
    # Manual input override
    if comp.input_amount is not None:
        return quantize_xaf(comp.input_amount)

    if comp.component_code == "ACCIDENT_RISK_EMPLOYER":
        # AT/MP is levied on pensionable base (same as PVID) — Décret N° 2014/2377
        return _calculate_accident_risk(
            cnps_contributory_base, ctx.rule_sets.get(_ACCIDENT_RISK_RULE), ctx.company_id
        )

    if comp.component_code == "FNE":
        # FNE patronale is levied on salaire brut (gross earnings)
        rs_fne = ctx.rule_sets.get(_FNE_EMPLOYER_RULE)
        if rs_fne is None:
            logger.warning(
                "Rule set '%s' not found for company %s; using fallback FNE-patronale rate %s.",
                _FNE_EMPLOYER_RULE, ctx.company_id, _DEFAULT_FNE_EMPLOYER_RATE,
            )
        return _calculate_rate_from_rule(gross_earnings, rs_fne, _DEFAULT_FNE_EMPLOYER_RATE)

    if comp.component_code == "EMPLOYER_AF":
        # Family Allowances (PF) are levied on pensionable base, capped at 750,000 XAF
        # — Décret N° 2014/2377, same ceiling as PVID
        rs_af = ctx.rule_sets.get(_AF_RULE)
        if rs_af is None:
            logger.warning(
                "Rule set '%s' not found for company %s; using fallback AF rate %s.",
                _AF_RULE, ctx.company_id, _DEFAULT_AF_RATE,
            )
        return _calculate_rate_from_rule(cnps_contributory_base, rs_af, _DEFAULT_AF_RATE)

    if comp.calculation_method_code == "fixed_amount":
        return quantize_xaf(comp.base_amount)

    if comp.calculation_method_code == "percentage":
        rate = comp.base_rate if comp.base_rate > 0 else Decimal("0")
        return quantize_xaf(gross_earnings * rate)

    # Generic rule_based: try base_rate if set
    if comp.calculation_method_code == "rule_based" and comp.base_rate > 0:
        return quantize_xaf(gross_earnings * comp.base_rate)

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
        amount = quantize_xaf(gross * rate)
        if bracket.cap_amount and bracket.cap_amount > 0:
            amount = min(amount, bracket.cap_amount)
        return max(amount, Decimal("0"))
    return max(quantize_xaf(gross * default_rate), Decimal("0"))


def _calculate_accident_risk(
    gross: Decimal, rule_set: RuleSetInput | None, company_id: int | None = None
) -> Decimal:
    if gross <= Decimal("0"):
        return Decimal("0")
    if rule_set and rule_set.brackets:
        bracket = rule_set.brackets[0]
        rate = bracket.rate if bracket.rate > 0 else _DEFAULT_ACCIDENT_RATE
        # Respect cap from bracket if present
        amount = quantize_xaf(gross * rate)
        if bracket.cap_amount and bracket.cap_amount > 0:
            amount = min(amount, bracket.cap_amount)
        return max(amount, Decimal("0"))
    else:
        logger.warning(
            "Rule set '%s' not found for company %s; using fallback AT/MP rate %s.",
            _ACCIDENT_RISK_RULE, company_id, _DEFAULT_ACCIDENT_RATE,
        )
        rate = _DEFAULT_ACCIDENT_RATE
    return max(quantize_xaf(gross * rate), Decimal("0"))
