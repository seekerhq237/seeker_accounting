"""Salary Deductions Engine — CCF (CFC) and FNE Employee (Salariale).

Computes employee-side salary deductions that sit between CNPS and IRPP in the
DGI monthly withholding table:
  - CCF / CFC (Crédit Foncier du Cameroun) — 1 % of taxable earnings
  - FNE Salariale (Fonds National de l'Emploi) — 1 % of taxable earnings

Base = taxable_gross (sum of earnings from is_taxable=True components only).
Non-taxable allowances (transport indemnity, housing indemnity, etc.) are
excluded from the CFC and FNE-Sal base per DGI methodology.

These deductions reduce the IRPP taxable base per DGI methodology:
  salaire_taxable = taxable_gross − CNPS_employee − CFC − FNE_employee
They are also separate line items on the pay slip that reduce net pay.

Rule set codes:
  CCF_MAIN          → rate for CFC_HLF component
  FNE_EMPLOYEE_MAIN → rate for FNE_EMPLOYEE component
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

_CCF_RULE = "CCF_MAIN"
_FNE_EMPLOYEE_RULE = "FNE_EMPLOYEE_MAIN"

# PROVISIONAL FALLBACKS — used only when rule sets are not configured.
_DEFAULT_CCF_RATE = Decimal("0.01")           # 1 % — Cameroon 2024
_DEFAULT_FNE_EMPLOYEE_RATE = Decimal("0.01")  # 1 % — Cameroon 2024


def run_salary_deductions_engine(
    ctx: EngineContext,
    taxable_gross: Decimal,
) -> list[EngineLineResult]:
    """Produce CCF and FNE employee deduction lines.

    Args:
        ctx: Engine context with components and rule sets.
        taxable_gross: Sum of earnings from is_taxable=True components only.
            Non-taxable allowances (transport, housing, etc.) are excluded.
    """
    results: list[EngineLineResult] = []

    if taxable_gross <= Decimal("0"):
        return results

    # CCF / CFC (Credit Foncier)
    ccf_comp = _find_component(ctx, "CFC_HLF")
    if ccf_comp is not None:
        rs_ccf = ctx.rule_sets.get(_CCF_RULE)
        if rs_ccf is None:
            logger.warning(
                "Rule set '%s' not found for company %s; using fallback CFC rate %s.",
                _CCF_RULE, ctx.company_id, _DEFAULT_CCF_RATE,
            )
        ccf_rate = _resolve_rate(rs_ccf, _DEFAULT_CCF_RATE)
        ccf_amount = quantize_xaf(taxable_gross * ccf_rate)
        if ccf_amount > Decimal("0"):
            results.append(
                EngineLineResult(
                    component_id=ccf_comp.component_id,
                    component_type_code="deduction",
                    calculation_basis=taxable_gross,
                    rate_applied=ccf_rate,
                    component_amount=ccf_amount,
                )
            )

    # FNE Employee (Salariale)
    fne_comp = _find_component(ctx, "FNE_EMPLOYEE")
    if fne_comp is not None:
        rs_fne = ctx.rule_sets.get(_FNE_EMPLOYEE_RULE)
        if rs_fne is None:
            logger.warning(
                "Rule set '%s' not found for company %s; using fallback FNE-Sal rate %s.",
                _FNE_EMPLOYEE_RULE, ctx.company_id, _DEFAULT_FNE_EMPLOYEE_RATE,
            )
        fne_rate = _resolve_rate(rs_fne, _DEFAULT_FNE_EMPLOYEE_RATE)
        fne_amount = quantize_xaf(taxable_gross * fne_rate)
        if fne_amount > Decimal("0"):
            results.append(
                EngineLineResult(
                    component_id=fne_comp.component_id,
                    component_type_code="deduction",
                    calculation_basis=taxable_gross,
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
