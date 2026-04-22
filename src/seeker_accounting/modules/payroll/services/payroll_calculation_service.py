"""PayrollCalculationService — orchestrates all calculation engines for one employee.

This service is pure computation. It does not persist anything. The PayrollRunService
calls this service per employee and then writes the results to payroll_run_employees
and payroll_run_lines.

Engine call order:
  1. Earnings (base salary + allowances)
  2. Overtime
  3. Benefits-in-kind
  4. CNPS (employee deduction + employer contribution)
  5. Salary deductions (CCF / CFC, FNE employee)
  6. TDL
  7. IRPP + CAC + CRTV
     taxable base = (taxable_gross − CNPS − CFC − FNE_employee) × (1 − abattement) − minimum_vital/12
     where taxable_gross = sum of earnings from is_taxable=True components only
  8. Employer contributions (FNE employer, Family Allowances, Accident Risk, etc.)
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from seeker_accounting.modules.payroll.engines.benefits_in_kind_engine import run_benefits_in_kind_engine
from seeker_accounting.modules.payroll.engines.cnps_engine import run_cnps_engine
from seeker_accounting.modules.payroll.engines.earnings_engine import run_earnings_engine
from seeker_accounting.modules.payroll.engines.employer_contribution_engine import (
    run_employer_contribution_engine,
)
from seeker_accounting.modules.payroll.engines.engine_types import (
    ComponentInput,
    EmployeeCalculationResult,
    EngineContext,
    EngineLineResult,
    RuleBracketInput,
    RuleSetInput,
)
from seeker_accounting.modules.payroll.engines.irpp_engine import run_irpp_engine
from seeker_accounting.modules.payroll.engines.overtime_engine import run_overtime_engine
from seeker_accounting.modules.payroll.engines.salary_deductions_engine import run_salary_deductions_engine
from seeker_accounting.modules.payroll.engines.tdl_engine import run_tdl_engine
from seeker_accounting.modules.payroll.models.employee_compensation_profile import EmployeeCompensationProfile
from seeker_accounting.modules.payroll.models.employee_component_assignment import EmployeeComponentAssignment
from seeker_accounting.modules.payroll.models.payroll_component import PayrollComponent
from seeker_accounting.modules.payroll.models.payroll_input_batch import PayrollInputBatch
from seeker_accounting.modules.payroll.models.payroll_rule_bracket import PayrollRuleBracket
from seeker_accounting.modules.payroll.models.payroll_rule_set import PayrollRuleSet

_ABATTEMENT_RULE = "DGI_IRPP_ABATTEMENT"

# PROVISIONAL FALLBACKS — used only when DGI_IRPP_ABATTEMENT rule set is missing.
# CGI Art. 32: 30 % professional expenses abattement
# CGI Art. 33: 500,000 XAF annual deduction (minimum vital non imposable)
_DEFAULT_ABATTEMENT_RATE = Decimal("0.30")
_DEFAULT_ANNUAL_MINIMUM_VITAL = Decimal("500000")


class PayrollCalculationService:
    """Orchestrates all engines and derives the payroll bases for one employee.

    Stateless — can be called repeatedly without side effects.
    """

    def calculate(
        self,
        profile: EmployeeCompensationProfile,
        assignments: list[EmployeeComponentAssignment],
        input_batches: list[PayrollInputBatch],
        rule_sets: list[PayrollRuleSet],
        period_year: int,
        period_month: int,
    ) -> EmployeeCalculationResult:
        """Run all engines and return the complete calculation result."""
        try:
            ctx = self._build_context(
                profile=profile,
                assignments=assignments,
                input_batches=input_batches,
                rule_sets=rule_sets,
                period_year=period_year,
                period_month=period_month,
            )
            return self._run_engines(ctx)
        except Exception as exc:
            result = EmployeeCalculationResult(employee_id=profile.employee_id)
            result.error_message = str(exc)
            return result

    # ── Context building ──────────────────────────────────────────────────────

    def _build_context(
        self,
        profile: EmployeeCompensationProfile,
        assignments: list[EmployeeComponentAssignment],
        input_batches: list[PayrollInputBatch],
        rule_sets: list[PayrollRuleSet],
        period_year: int,
        period_month: int,
    ) -> EngineContext:
        # Build variable input map: {(employee_id, component_id): (amount, quantity)}
        input_map: dict[tuple[int, int], tuple[Decimal, Decimal | None]] = {}
        for batch in input_batches:
            for line in batch.lines:
                key = (line.employee_id, line.component_id)
                existing = input_map.get(key)
                amt = Decimal(str(line.input_amount))
                qty = Decimal(str(line.input_quantity)) if line.input_quantity is not None else None
                if existing is None:
                    input_map[key] = (amt, qty)
                else:
                    # Sum amounts for same (employee, component) across batches
                    prev_amt, prev_qty = existing
                    new_qty = (prev_qty or Decimal("0")) + (qty or Decimal("0")) if (prev_qty or qty) else None
                    input_map[key] = (prev_amt + amt, new_qty)

        # Build component inputs from assignments
        basic_salary = Decimal(str(profile.basic_salary))
        components: list[ComponentInput] = []
        for assignment in assignments:
            comp = assignment.component
            emp_input = input_map.get((profile.employee_id, comp.id))

            # Resolve base_amount: use override if set, else fall back to
            # profile basic_salary for BASE_SALARY component (the canonical
            # fixed-amount earning whose amount is defined on the profile).
            if assignment.override_amount:
                resolved_base_amount = Decimal(str(assignment.override_amount))
            elif comp.component_code == "BASE_SALARY":
                resolved_base_amount = basic_salary
            else:
                resolved_base_amount = Decimal("0")

            components.append(
                ComponentInput(
                    component_id=comp.id,
                    component_code=comp.component_code,
                    component_name=comp.component_name,
                    component_type_code=comp.component_type_code,
                    calculation_method_code=comp.calculation_method_code,
                    is_taxable=comp.is_taxable,
                    is_pensionable=comp.is_pensionable,
                    base_amount=resolved_base_amount,
                    base_rate=Decimal(str(assignment.override_rate)) if assignment.override_rate else Decimal("0"),
                    rule_code=None,
                    input_amount=emp_input[0] if emp_input else None,
                    input_quantity=emp_input[1] if emp_input else None,
                )
            )

        # Build rule set map
        rule_set_map: dict[str, RuleSetInput] = {}
        for rs in rule_sets:
            brackets = [
                RuleBracketInput(
                    lower_bound=(
                        Decimal(str(b.lower_bound_amount))
                        if b.lower_bound_amount is not None
                        else Decimal("0")
                    ),
                    upper_bound=(
                        Decimal(str(b.upper_bound_amount))
                        if b.upper_bound_amount is not None
                        else None
                    ),
                    rate=(
                        Decimal(str(b.rate_percent)) / Decimal("100")
                        if b.rate_percent is not None
                        else Decimal("0")
                    ),
                    fixed_amount=Decimal(str(b.fixed_amount)) if b.fixed_amount is not None else Decimal("0"),
                    deduction_amount=Decimal(str(b.deduction_amount)) if b.deduction_amount is not None else Decimal("0"),
                    cap_amount=Decimal(str(b.cap_amount)) if b.cap_amount is not None else None,
                )
                for b in sorted(rs.brackets, key=lambda x: x.line_number)
            ]
            rule_set_map[rs.rule_code] = RuleSetInput(
                rule_set_id=rs.id,
                rule_code=rs.rule_code,
                rule_type_code=rs.rule_type_code,
                calculation_basis_code=rs.calculation_basis_code,
                brackets=brackets,
            )

        return EngineContext(
            company_id=profile.company_id,
            employee_id=profile.employee_id,
            period_year=period_year,
            period_month=period_month,
            basic_salary=basic_salary,
            currency_code=profile.currency_code,
            components=components,
            rule_sets=rule_set_map,
            number_of_parts=Decimal(str(getattr(profile, "number_of_parts", 1) or 1)),
        )

    # ── Engine orchestration ──────────────────────────────────────────────────

    def _run_engines(self, ctx: EngineContext) -> EmployeeCalculationResult:
        result = EmployeeCalculationResult(employee_id=ctx.employee_id)
        all_lines: list[EngineLineResult] = []

        # 1. Earnings (base salary + allowances)
        all_lines.extend(run_earnings_engine(ctx))

        # 2. Overtime
        all_lines.extend(run_overtime_engine(ctx))

        # 3. Benefits-in-kind
        all_lines.extend(run_benefits_in_kind_engine(ctx))

        # Derive gross earnings from earning lines so far
        gross_earnings = sum(
            (l.component_amount for l in all_lines if l.component_type_code == "earning"),
            Decimal("0"),
        )

        # Determine CNPS contributory base: earnings from pensionable components
        cnps_base = self._compute_cnps_base(ctx, all_lines)

        # 4. CNPS (employee deduction + employer contribution)
        cnps_lines = run_cnps_engine(ctx, cnps_contributory_base=cnps_base)
        all_lines.extend(cnps_lines)

        # Employee CNPS deduction reduces the IRPP taxable base
        employee_cnps = sum(
            (l.component_amount for l in cnps_lines if l.component_type_code == "deduction"),
            Decimal("0"),
        )

        # 5. Salary deductions (CCF / CFC, FNE Employee)
        salary_deduction_lines = run_salary_deductions_engine(ctx, gross_earnings=gross_earnings)
        all_lines.extend(salary_deduction_lines)

        # Sum CFC + FNE employee deduction amounts (they reduce the IRPP taxable base)
        # Explicit filter: only CFC_HLF and FNE_EMPLOYEE reduce the IRPP base per DGI methodology.
        _cfc_fne_ids = {
            comp.component_id for comp in ctx.components
            if comp.component_code in ("CFC_HLF", "FNE_EMPLOYEE")
        }
        cfc_fne_total = sum(
            (l.component_amount for l in salary_deduction_lines
             if l.component_id in _cfc_fne_ids),
            Decimal("0"),
        )

        # TDL base = gross earnings (full earnings before deductions)
        tdl_base = gross_earnings

        # IRPP taxable base calculation per DGI methodology:
        #   taxable_gross = sum of earnings from is_taxable=True components only
        #   salaire_taxable = taxable_gross - employee_CNPS - CFC - FNE_employee
        #   after_abattement = salaire_taxable × (1 - abattement_rate)   [CGI Art. 32]
        #   monthly_net_imposable = after_abattement - (annual_deduction / 12)  [CGI Art. 33]
        taxable_component_ids = {
            comp.component_id for comp in ctx.components if comp.is_taxable
        }
        taxable_gross = sum(
            (l.component_amount for l in all_lines
             if l.component_type_code == "earning" and l.component_id in taxable_component_ids),
            Decimal("0"),
        )
        abattement_rate, annual_deduction = self._resolve_abattement(ctx)
        salaire_taxable = max(taxable_gross - employee_cnps - cfc_fne_total, Decimal("0"))
        after_abattement = (salaire_taxable * (Decimal("1") - abattement_rate)).quantize(Decimal("0.0001"))
        monthly_deduction = (annual_deduction / Decimal("12")).quantize(Decimal("0.0001"))
        taxable_salary_base = max(after_abattement - monthly_deduction, Decimal("0"))

        # 6. TDL
        all_lines.extend(run_tdl_engine(ctx, tdl_base=tdl_base))

        # 7. IRPP + CAC + CRTV
        all_lines.extend(
            run_irpp_engine(ctx, taxable_salary_base=taxable_salary_base, gross_earnings=gross_earnings)
        )

        # 8. Employer contributions (FNE employer, Family Allowances, Accident Risk, etc.)
        all_lines.extend(run_employer_contribution_engine(ctx, gross_earnings=gross_earnings))

        # Aggregate all lines
        result.lines = all_lines
        result.gross_earnings = gross_earnings
        result.taxable_salary_base = taxable_salary_base
        result.tdl_base = tdl_base
        result.cnps_contributory_base = cnps_base

        result.total_earnings = sum(
            (l.component_amount for l in all_lines if l.component_type_code == "earning"),
            Decimal("0"),
        )
        result.total_employee_deductions = sum(
            (l.component_amount for l in all_lines if l.component_type_code == "deduction"),
            Decimal("0"),
        )
        result.total_taxes = sum(
            (l.component_amount for l in all_lines if l.component_type_code == "tax"),
            Decimal("0"),
        )
        result.total_employer_contributions = sum(
            (l.component_amount for l in all_lines if l.component_type_code == "employer_contribution"),
            Decimal("0"),
        )

        result.net_payable = max(
            result.total_earnings - result.total_employee_deductions - result.total_taxes,
            Decimal("0"),
        )
        result.employer_cost_base = gross_earnings + result.total_employer_contributions

        return result

    def _resolve_abattement(self, ctx: EngineContext) -> tuple[Decimal, Decimal]:
        """Read abattement rate and annual minimum vital deduction from DGI_IRPP_ABATTEMENT rule set.

        Returns (abattement_rate_decimal, annual_deduction_amount).
        Falls back to provisional defaults if the rule set is missing.
        """
        rule_set = ctx.rule_sets.get(_ABATTEMENT_RULE)
        if rule_set and rule_set.brackets:
            bracket = rule_set.brackets[0]
            rate = bracket.rate if bracket.rate > 0 else _DEFAULT_ABATTEMENT_RATE
            deduction = bracket.deduction_amount if bracket.deduction_amount > 0 else _DEFAULT_ANNUAL_MINIMUM_VITAL
            return rate, deduction
        return _DEFAULT_ABATTEMENT_RATE, _DEFAULT_ANNUAL_MINIMUM_VITAL

    def _compute_cnps_base(
        self, ctx: EngineContext, earning_lines: list[EngineLineResult]
    ) -> Decimal:
        """Sum earnings from components flagged as pensionable."""
        pensionable_ids = {
            comp.component_id for comp in ctx.components if comp.is_pensionable
        }
        return sum(
            (l.component_amount for l in earning_lines if l.component_id in pensionable_ids),
            Decimal("0"),
        )
