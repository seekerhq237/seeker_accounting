"""Salary Deductions Engine — CCF (CFC) and FNE Employee (Salariale).

Computes employee-side salary deductions that sit between CNPS and IRPP in the
DGI monthly withholding table:
  - CCF / CFC (Crédit Foncier du Cameroun) — 1 % of gross salary
  - FNE Salariale (Fonds National de l'Emploi) — 1 % of gross salary

These deductions reduce the IRPP taxable base per DGI methodology:
  salaire_taxable = taxable_gross − CNPS_employee − CFC − FNE_employee
They are also separate line items on the pay slip that reduce net pay.

Rule set codes:
  CCF_MAIN          → rate for CFC_HLF component
  FNE_EMPLOYEE_MAIN → rate for FNE_EMPLOYEE component
"""

from __future__ import annotations

from decimal import Decimal

from seeker_accounting.modules.payroll.engines.engine_types import (
    EngineContext,
    EngineLineResult,
    RuleSetInput,
)

_CCF_RULE = "CCF_MAIN"
_FNE_EMPLOYEE_RULE = "FNE_EMPLOYEE_MAIN"

# PROVISIONAL FALLBACKS — used only when rule sets are not configured.
_DEFAULT_CCF_RATE = Decimal("0.01")           # 1 % — Cameroon 2024
_DEFAULT_FNE_EMPLOYEE_RATE = Decimal("0.01")  # 1 % — Cameroon 2024


def run_salary_deductions_engine(
    ctx: EngineContext,
    gross_earnings: Decimal,
) -> list[EngineLineResult]:
    """Produce CCF and FNE employee deduction lines."""
    results: list[EngineLineResult] = []

    if gross_earnings <= Decimal("0"):
        return results

    # CCF / CFC (Credit Foncier)
    ccf_comp = _find_component(ctx, "CFC_HLF")
    if ccf_comp is not None:
        ccf_rate = _resolve_rate(ctx.rule_sets.get(_CCF_RULE), _DEFAULT_CCF_RATE)
        ccf_amount = (gross_earnings * ccf_rate).quantize(Decimal("0.0001"))
        if ccf_amount > Decimal("0"):
            results.append(
                EngineLineResult(
                    component_id=ccf_comp.component_id,
                    component_type_code="deduction",
                    calculation_basis=gross_earnings,
                    rate_applied=ccf_rate,
                    component_amount=ccf_amount,
                )
            )

    # FNE Employee (Salariale)
    fne_comp = _find_component(ctx, "FNE_EMPLOYEE")
    if fne_comp is not None:
        fne_rate = _resolve_rate(ctx.rule_sets.get(_FNE_EMPLOYEE_RULE), _DEFAULT_FNE_EMPLOYEE_RATE)
        fne_amount = (gross_earnings * fne_rate).quantize(Decimal("0.0001"))
        if fne_amount > Decimal("0"):
            results.append(
                EngineLineResult(
                    component_id=fne_comp.component_id,
                    component_type_code="deduction",
                    calculation_basis=gross_earnings,
                    rate_applied=fne_rate,
                    component_amount=fne_amount,
                )
            )

    return results


def _find_component(ctx: EngineContext, code: str):
    for comp in ctx.components:
        if comp.component_code == code:
            return comp
    return None


def _resolve_rate(rule_set: RuleSetInput | None, default: Decimal) -> Decimal:
    if rule_set and rule_set.brackets:
        bracket = rule_set.brackets[0]
        if bracket.rate > 0:
            return bracket.rate
    return default
