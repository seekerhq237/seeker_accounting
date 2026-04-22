"""IRPP Engine (Impôt sur le Revenu des Personnes Physiques — Cameroon income tax).

Computes IRPP (personal income tax) using the DGI_IRPP_MAIN progressive bracket
rule set, with quotient familial (family parts) support.

Computation steps (as called by the PayrollCalculationService):
  1. taxable_salary_base is pre-computed externally:
     taxable_salary_base = max((taxable_gross - CNPS - CFC - FNE) × (1 − abattement) − minimum_vital/12, 0)
  2. Apply quotient familial:
     a. annual_base = taxable_salary_base × 12
     b. annual_per_part = annual_base / number_of_parts
     c. Apply progressive brackets from DGI_IRPP_MAIN to annual_per_part
     d. annual_tax = tax_per_part × number_of_parts
     e. monthly_irpp = annual_tax / 12
  3. CAC (Centimes Additionnels Communaux) = 10 % of IRPP (if CAC component exists)
  4. CRTV = bracket-based monthly amount from CRTV_MAIN (keyed on gross salary)

gross_earnings is passed separately for CRTV bracket lookup (CRTV schedule is
keyed on monthly gross salary, not on the IRPP taxable base).
"""

from __future__ import annotations

from decimal import Decimal

from seeker_accounting.modules.payroll.engines.engine_types import (
    EngineContext,
    EngineLineResult,
    RuleSetInput,
)

_IRPP_RULE = "DGI_IRPP_MAIN"
_CRTV_RULE = "CRTV_MAIN"

# PROVISIONAL FALLBACK — CAC rate for Cameroon (10 % of IRPP liability).
# Used only when the CAC component has no base_rate configured.  In a properly
# seeded environment the CAC component carries base_rate = 0.10.  Update via
# seeded payroll component data before going live in any jurisdiction.
_CAC_RATE_FALLBACK = Decimal("0.10")  # 10 % — Cameroon 2024


def run_irpp_engine(
    ctx: EngineContext,
    taxable_salary_base: Decimal,
    gross_earnings: Decimal | None = None,
) -> list[EngineLineResult]:
    """Produce IRPP, CAC, and CRTV deduction lines.

    Args:
        ctx: Engine context with components and rule sets.
        taxable_salary_base: Monthly net imposable (after CNPS, abattement, minimum vital).
        gross_earnings: Monthly gross earnings for CRTV bracket lookup.  Falls back
            to taxable_salary_base if not provided (backward compatibility).
    """
    results: list[EngineLineResult] = []

    irpp_comp = _find_component(ctx, "IRPP")
    if irpp_comp is None:
        return results

    # Guard: IRPP on zero or negative base produces zero
    if taxable_salary_base <= Decimal("0"):
        # Still evaluate CRTV — it applies regardless of IRPP-zero threshold
        _append_crtv(ctx, results, gross_earnings or Decimal("0"))
        return results

    rule_set = ctx.rule_sets.get(_IRPP_RULE)
    irpp_amount = _calculate_bracket_tax(taxable_salary_base, rule_set, ctx.number_of_parts)

    if irpp_amount > 0:
        results.append(
            EngineLineResult(
                component_id=irpp_comp.component_id,
                component_type_code="tax",
                calculation_basis=taxable_salary_base,
                rate_applied=None,
                component_amount=irpp_amount,
            )
        )

        # CAC — rate is read from the component's configured base_rate.
        # Falls back to _CAC_RATE_FALLBACK only when base_rate is zero/absent.
        cac_comp = _find_component(ctx, "CAC")
        if cac_comp is not None:
            cac_rate = cac_comp.base_rate if cac_comp.base_rate > 0 else _CAC_RATE_FALLBACK
            cac_amount = (irpp_amount * cac_rate).quantize(Decimal("0.0001"))
            results.append(
                EngineLineResult(
                    component_id=cac_comp.component_id,
                    component_type_code="tax",
                    calculation_basis=irpp_amount,
                    rate_applied=cac_rate,
                    component_amount=cac_amount,
                )
            )

    # CRTV — bracket-based or fixed monthly contribution
    _append_crtv(ctx, results, gross_earnings or taxable_salary_base)

    return results


def _append_crtv(
    ctx: EngineContext,
    results: list[EngineLineResult],
    gross_for_lookup: Decimal,
) -> None:
    """Resolve CRTV from CRTV_MAIN rule set brackets, falling back to fixed amount."""
    crtv_comp = _find_component(ctx, "CRTV")
    if crtv_comp is None:
        return

    # Try bracket-based lookup first (CRTV schedule keyed on gross salary)
    crtv_rule = ctx.rule_sets.get(_CRTV_RULE)
    if crtv_rule and crtv_rule.brackets:
        crtv_amount = _resolve_crtv_bracket(gross_for_lookup, crtv_rule)
    else:
        # Legacy fallback: fixed amount from component or input
        crtv_amount = _resolve_fixed(crtv_comp)

    if crtv_amount > Decimal("0"):
        results.append(
            EngineLineResult(
                component_id=crtv_comp.component_id,
                component_type_code="deduction",
                calculation_basis=gross_for_lookup,
                rate_applied=None,
                component_amount=crtv_amount,
            )
        )


def _find_component(ctx: EngineContext, code: str):
    for comp in ctx.components:
        if comp.component_code == code:
            return comp
    return None


def _resolve_fixed(comp) -> Decimal:
    if comp.input_amount is not None:
        return comp.input_amount.quantize(Decimal("0.0001"))
    return comp.base_amount.quantize(Decimal("0.0001"))


def _resolve_crtv_bracket(gross: Decimal, rule_set: RuleSetInput) -> Decimal:
    """Find the CRTV fixed amount from the bracket whose range covers the gross salary.

    Bracket boundaries are upper-inclusive: a gross that equals the upper bound
    of bracket N stays in bracket N (verified against DGI barème DSSI).
    """
    matched_amount = Decimal("0")
    for bracket in rule_set.brackets:
        lower = bracket.lower_bound
        upper = bracket.upper_bound
        if gross < lower:
            break
        if upper is None or gross <= upper:
            matched_amount = bracket.fixed_amount
            break
        matched_amount = bracket.fixed_amount
    return matched_amount.quantize(Decimal("0.0001"))


def _calculate_bracket_tax(
    base: Decimal,
    rule_set: RuleSetInput | None,
    number_of_parts: Decimal = Decimal("1"),
) -> Decimal:
    """Apply progressive IRPP brackets with quotient familial.

    Steps:
      1. Annualize: annual_base = base × 12
      2. Divide by parts: annual_per_part = annual_base / number_of_parts
      3. Apply progressive brackets to annual_per_part → tax_per_part
      4. Multiply back: annual_tax = tax_per_part × number_of_parts
      5. De-annualize: monthly_tax = annual_tax / 12
    """
    if rule_set is None or not rule_set.brackets:
        return Decimal("0")

    parts = max(number_of_parts, Decimal("1"))

    # Annualize then divide by family parts
    annual_base = base * 12
    annual_per_part = annual_base / parts

    tax_per_part = Decimal("0")
    for bracket in rule_set.brackets:
        if annual_per_part <= bracket.lower_bound:
            break
        upper = bracket.upper_bound if bracket.upper_bound is not None else annual_per_part
        taxable_in_bracket = min(annual_per_part, upper) - bracket.lower_bound
        if taxable_in_bracket <= 0:
            continue

        bracket_tax = taxable_in_bracket * bracket.rate - bracket.deduction_amount
        if bracket.cap_amount and bracket.cap_amount > 0:
            bracket_tax = min(bracket_tax, bracket.cap_amount)
        tax_per_part += max(bracket_tax, Decimal("0"))

    # Multiply back by parts and de-annualize
    annual_tax = tax_per_part * parts
    monthly_tax = (annual_tax / 12).quantize(Decimal("0.0001"))
    return monthly_tax
