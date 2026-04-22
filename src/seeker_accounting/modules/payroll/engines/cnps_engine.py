"""CNPS Engine (Caisse Nationale de Prévoyance Sociale — Cameroon pension).

Computes both the employee and employer CNPS pension contributions.

Inputs:
  cnps_contributory_base: sum of earnings flagged is_pensionable=True
  rule sets: CNPS_EMPLOYEE_MAIN and CNPS_EMPLOYER_MAIN

Rate resolution (from rule set brackets):
  - First bracket covering the base is used
  - Rate is a decimal (e.g. 0.042 for 4.2%)
  - Cap is applied if bracket defines a cap_amount

Default fallback (if no rule set is configured):
  - Employee: 4.2 %
  - Employer: 4.2 %
  - Cap: 750,000 XAF/month contributory salary

Total PVID is 8.4 % split equally: employee 4.2 % + employer 4.2 %.
"""

from __future__ import annotations

from decimal import Decimal

from seeker_accounting.modules.payroll.engines.engine_types import (
    EngineContext,
    EngineLineResult,
    RuleSetInput,
)

_CNPS_EMPLOYEE_RULE = "CNPS_EMPLOYEE_MAIN"
_CNPS_EMPLOYER_RULE = "CNPS_EMPLOYER_MAIN"

# PROVISIONAL FALLBACK — Cameroon 2024 statutory rates.
# These values are used ONLY when CNPS_EMPLOYEE_MAIN / CNPS_EMPLOYER_MAIN rule sets
# are not configured in the company's payroll rule data.  In a properly seeded
# environment (CameroonPayrollSeedService or equivalent statutory pack) these
# defaults are never reached.  Replace with correct seeded rule sets before
# going live in any jurisdiction.
_DEFAULT_EMPLOYEE_RATE = Decimal("0.042")   # 4.2 % employee CNPS — Cameroon 2024
_DEFAULT_EMPLOYER_RATE = Decimal("0.042")   # 4.2 % employer CNPS — Cameroon 2024 (total PVID 8.4 % split equally)
_DEFAULT_CAP = Decimal("750000")            # monthly contributory salary cap (XAF) — Cameroon 2024


def run_cnps_engine(
    ctx: EngineContext,
    cnps_contributory_base: Decimal,
) -> list[EngineLineResult]:
    """Produce CNPS employee deduction and employer contribution lines."""
    results: list[EngineLineResult] = []

    # Find the CNPS component IDs from the context
    employee_comp = _find_component(ctx, "EMPLOYEE_CNPS")
    employer_comp = _find_component(ctx, "EMPLOYER_CNPS")

    # Guard: CNPS cannot be negative
    if cnps_contributory_base <= Decimal("0"):
        return results

    if employee_comp is not None:
        emp_rate, emp_base_cap, emp_result_cap = _resolve_rate_cap(ctx.rule_sets.get(_CNPS_EMPLOYEE_RULE))
        if emp_rate is None:
            emp_rate, emp_base_cap, emp_result_cap = _DEFAULT_EMPLOYEE_RATE, _DEFAULT_CAP, None
        capped_base = min(cnps_contributory_base, emp_base_cap) if emp_base_cap else cnps_contributory_base
        amount = max((capped_base * emp_rate).quantize(Decimal("0.0001")), Decimal("0"))
        if emp_result_cap and emp_result_cap > 0:
            amount = min(amount, emp_result_cap)
        results.append(
            EngineLineResult(
                component_id=employee_comp.component_id,
                component_type_code="deduction",
                calculation_basis=capped_base,
                rate_applied=emp_rate,
                component_amount=amount,
            )
        )

    if employer_comp is not None:
        er_rate, er_base_cap, er_result_cap = _resolve_rate_cap(ctx.rule_sets.get(_CNPS_EMPLOYER_RULE))
        if er_rate is None:
            er_rate, er_base_cap, er_result_cap = _DEFAULT_EMPLOYER_RATE, _DEFAULT_CAP, None
        capped_base = min(cnps_contributory_base, er_base_cap) if er_base_cap else cnps_contributory_base
        amount = max((capped_base * er_rate).quantize(Decimal("0.0001")), Decimal("0"))
        if er_result_cap and er_result_cap > 0:
            amount = min(amount, er_result_cap)
        results.append(
            EngineLineResult(
                component_id=employer_comp.component_id,
                component_type_code="employer_contribution",
                calculation_basis=capped_base,
                rate_applied=er_rate,
                component_amount=amount,
            )
        )

    return results


def _find_component(ctx: EngineContext, code: str):
    for comp in ctx.components:
        if comp.component_code == code:
            return comp
    return None


def _resolve_rate_cap(rule_set: RuleSetInput | None) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    """Return (rate, base_cap, result_cap) from the first bracket of a CNPS rule set.

    base_cap:   salary ceiling (upper_bound — e.g. 750,000 XAF)
    result_cap: maximum contribution amount (cap_amount — e.g. 31,500 XAF)
    """
    if rule_set is None or not rule_set.brackets:
        return None, None, None
    bracket = rule_set.brackets[0]
    rate = bracket.rate if bracket.rate > 0 else None
    base_cap = bracket.upper_bound if bracket.upper_bound and bracket.upper_bound > 0 else None
    result_cap = bracket.cap_amount if bracket.cap_amount and bracket.cap_amount > 0 else None
    return rate, base_cap, result_cap
