"""Unit tests for payroll calculation engines.

Pure-computation tests — no database, no ORM sessions, no mocks of external
services.  Each test constructs engine types directly and calls the engine
function under test.

Covers:
  - Earnings engine
  - Overtime engine (multi-tier Cameroon + legacy)
  - Benefits-in-kind engine
  - CNPS engine (employee + employer, cap behaviour)
  - Salary deductions engine (CFC + FNE employee)
  - TDL engine (bracket lookup)
  - IRPP engine (progressive brackets, quotient familial, CAC, CRTV)
  - Employer contribution engine (FNE patronale, AF, accident risk)
"""

from __future__ import annotations

import unittest
from decimal import Decimal

from seeker_accounting.modules.payroll.engines.engine_types import (
    ComponentInput,
    EngineContext,
    EngineLineResult,
    RuleBracketInput,
    RuleSetInput,
)
from seeker_accounting.modules.payroll.engines.earnings_engine import run_earnings_engine
from seeker_accounting.modules.payroll.engines.overtime_engine import run_overtime_engine
from seeker_accounting.modules.payroll.engines.benefits_in_kind_engine import run_benefits_in_kind_engine
from seeker_accounting.modules.payroll.engines.cnps_engine import run_cnps_engine
from seeker_accounting.modules.payroll.engines.salary_deductions_engine import run_salary_deductions_engine
from seeker_accounting.modules.payroll.engines.tdl_engine import run_tdl_engine
from seeker_accounting.modules.payroll.engines.irpp_engine import run_irpp_engine
from seeker_accounting.modules.payroll.engines.employer_contribution_engine import (
    run_employer_contribution_engine,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

_ID_SEQ = 0


def _D(v: str) -> Decimal:
    return Decimal(v)


def _next_id() -> int:
    global _ID_SEQ
    _ID_SEQ += 1
    return _ID_SEQ


def _make_component(
    code: str,
    type_code: str = "earning",
    method_code: str = "fixed_amount",
    *,
    is_taxable: bool = True,
    is_pensionable: bool = True,
    base_amount: str = "0",
    base_rate: str = "0",
    input_amount: str | None = None,
    input_quantity: str | None = None,
    component_id: int | None = None,
) -> ComponentInput:
    return ComponentInput(
        component_id=component_id or _next_id(),
        component_code=code,
        component_name=code,
        component_type_code=type_code,
        calculation_method_code=method_code,
        is_taxable=is_taxable,
        is_pensionable=is_pensionable,
        base_amount=_D(base_amount),
        base_rate=_D(base_rate),
        rule_code=None,
        input_amount=_D(input_amount) if input_amount is not None else None,
        input_quantity=_D(input_quantity) if input_quantity is not None else None,
    )


def _make_bracket(
    lower: str = "0",
    upper: str | None = None,
    rate_pct: str = "0",
    fixed: str = "0",
    deduction: str = "0",
    cap: str | None = None,
) -> RuleBracketInput:
    """Rate is given as a percentage (e.g. '10.00' for 10%) and converted to decimal."""
    return RuleBracketInput(
        lower_bound=_D(lower),
        upper_bound=_D(upper) if upper is not None else None,
        rate=_D(rate_pct) / _D("100"),
        fixed_amount=_D(fixed),
        deduction_amount=_D(deduction),
        cap_amount=_D(cap) if cap is not None else None,
    )


def _make_rule_set(
    code: str,
    type_code: str = "levy",
    basis: str = "gross_salary",
    brackets: list[RuleBracketInput] | None = None,
) -> RuleSetInput:
    return RuleSetInput(
        rule_set_id=_next_id(),
        rule_code=code,
        rule_type_code=type_code,
        calculation_basis_code=basis,
        brackets=brackets or [],
    )


def _make_context(
    basic_salary: str = "300000",
    components: list[ComponentInput] | None = None,
    rule_sets: dict[str, RuleSetInput] | None = None,
    number_of_parts: str = "1",
) -> EngineContext:
    return EngineContext(
        company_id=1,
        employee_id=1,
        period_year=2024,
        period_month=6,
        basic_salary=_D(basic_salary),
        currency_code="XAF",
        components=components or [],
        rule_sets=rule_sets or {},
        number_of_parts=_D(number_of_parts),
    )


def _cameroon_irpp_rule_sets() -> dict[str, RuleSetInput]:
    """Canonical Cameroon 2024 rule sets for IRPP-related engines."""
    return {
        "DGI_IRPP_MAIN": _make_rule_set(
            "DGI_IRPP_MAIN", "pit", "taxable_gross",
            [
                _make_bracket("0", "2000000", "10.00"),
                _make_bracket("2000000", "3000000", "15.00"),
                _make_bracket("3000000", "5000000", "25.00"),
                _make_bracket("5000000", None, "35.00"),
            ],
        ),
        "DGI_IRPP_ABATTEMENT": _make_rule_set(
            "DGI_IRPP_ABATTEMENT", "abattement", "taxable_gross",
            [_make_bracket(deduction="500000", rate_pct="30.00")],
        ),
        "CRTV_MAIN": _make_rule_set(
            "CRTV_MAIN", "levy", "gross_salary",
            [
                _make_bracket("0", "50000", fixed="0"),
                _make_bracket("50000", "100000", fixed="750"),
                _make_bracket("100000", "200000", fixed="1950"),
                _make_bracket("200000", "300000", fixed="3250"),
                _make_bracket("300000", "500000", fixed="4550"),
                _make_bracket("500000", "700000", fixed="5850"),
                _make_bracket("700000", "800000", fixed="9750"),
                _make_bracket("800000", "1000000", fixed="12350"),
                _make_bracket("1000000", None, fixed="13000"),
            ],
        ),
        "TDL_MAIN": _make_rule_set(
            "TDL_MAIN", "levy", "gross_salary",
            [
                _make_bracket("0", "50000", fixed="0"),
                _make_bracket("50000", "208333", fixed="167"),
                _make_bracket("208333", None, fixed="250"),
            ],
        ),
    }


def _cameroon_cnps_rule_sets() -> dict[str, RuleSetInput]:
    """Canonical Cameroon 2024 CNPS rule sets."""
    return {
        "CNPS_EMPLOYEE_MAIN": _make_rule_set(
            "CNPS_EMPLOYEE_MAIN", "pension_employee", "gross_salary",
            [_make_bracket("0", "750000", "4.20", cap="31500")],
        ),
        "CNPS_EMPLOYER_MAIN": _make_rule_set(
            "CNPS_EMPLOYER_MAIN", "pension_employer", "gross_salary",
            [_make_bracket("0", "750000", "4.20", cap="31500")],
        ),
    }


def _cameroon_deduction_rule_sets() -> dict[str, RuleSetInput]:
    """Canonical Cameroon 2024 salary deduction rule sets."""
    return {
        "CCF_MAIN": _make_rule_set(
            "CCF_MAIN", "levy", "gross_salary",
            [_make_bracket("0", None, "1.00")],
        ),
        "FNE_EMPLOYEE_MAIN": _make_rule_set(
            "FNE_EMPLOYEE_MAIN", "levy", "gross_salary",
            [_make_bracket("0", None, "1.00")],
        ),
    }


def _cameroon_employer_rule_sets() -> dict[str, RuleSetInput]:
    """Canonical Cameroon 2024 employer contribution rule sets."""
    return {
        "FNE_EMPLOYER_MAIN": _make_rule_set(
            "FNE_EMPLOYER_MAIN", "levy", "gross_salary",
            [_make_bracket("0", None, "2.50")],
        ),
        "AF_MAIN": _make_rule_set(
            "AF_MAIN", "family_benefit", "gross_salary",
            [_make_bracket("0", "750000", "7.00", cap="52500")],
        ),
        "ACCIDENT_RISK_STANDARD": _make_rule_set(
            "ACCIDENT_RISK_STANDARD", "accident_risk", "gross_salary",
            [_make_bracket("0", None, "1.75")],
        ),
    }


def _cameroon_overtime_rule_sets() -> dict[str, RuleSetInput]:
    """Canonical Cameroon 2024 overtime rule sets."""
    return {
        "OVERTIME_STANDARD": _make_rule_set(
            "OVERTIME_STANDARD", "overtime", "basic_salary",
            [_make_bracket(rate_pct="50.00")],
        ),
        "OVERTIME_DAY_T1": _make_rule_set(
            "OVERTIME_DAY_T1", "overtime", "basic_salary",
            [_make_bracket(rate_pct="20.00")],
        ),
        "OVERTIME_DAY_T2": _make_rule_set(
            "OVERTIME_DAY_T2", "overtime", "basic_salary",
            [_make_bracket(rate_pct="30.00")],
        ),
        "OVERTIME_DAY_T3": _make_rule_set(
            "OVERTIME_DAY_T3", "overtime", "basic_salary",
            [_make_bracket(rate_pct="40.00")],
        ),
        "OVERTIME_NIGHT": _make_rule_set(
            "OVERTIME_NIGHT", "overtime", "basic_salary",
            [_make_bracket(rate_pct="50.00")],
        ),
    }


def _line_by_code(lines: list[EngineLineResult], ctx: EngineContext, code: str) -> EngineLineResult | None:
    """Find an engine line result by component code."""
    code_to_id = {c.component_code: c.component_id for c in ctx.components}
    target_id = code_to_id.get(code)
    if target_id is None:
        return None
    for line in lines:
        if line.component_id == target_id:
            return line
    return None


# ── Earnings Engine ───────────────────────────────────────────────────────────

class TestEarningsEngine(unittest.TestCase):

    def test_base_salary_fixed_amount(self):
        comp = _make_component("BASE_SALARY", base_amount="300000")
        ctx = _make_context("300000", [comp])
        lines = run_earnings_engine(ctx)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].component_amount, _D("300000.0000"))

    def test_percentage_allowance(self):
        comp = _make_component(
            "SENIORITY_BONUS", method_code="percentage", base_rate="0.10",
        )
        ctx = _make_context("300000", [comp])
        lines = run_earnings_engine(ctx)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].component_amount, _D("30000.0000"))
        self.assertEqual(lines[0].rate_applied, _D("0.10"))

    def test_input_amount_overrides_base(self):
        comp = _make_component("BASE_SALARY", base_amount="300000", input_amount="350000")
        ctx = _make_context("300000", [comp])
        lines = run_earnings_engine(ctx)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].component_amount, _D("350000.0000"))

    def test_manual_input_zero_when_no_input(self):
        comp = _make_component("BONUS", method_code="manual_input")
        ctx = _make_context("300000", [comp])
        lines = run_earnings_engine(ctx)
        # manual_input with no input_amount still produces a line (amount=0)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].component_amount, _D("0"))

    def test_delegated_codes_skipped(self):
        comps = [
            _make_component("OVERTIME"),
            _make_component("OVERTIME_DAY_T1"),
            _make_component("HOUSING_BIK"),
            _make_component("TRANSPORT_BIK"),
        ]
        ctx = _make_context("300000", comps)
        lines = run_earnings_engine(ctx)
        self.assertEqual(len(lines), 0)

    def test_non_earning_types_skipped(self):
        comp = _make_component("EMPLOYEE_CNPS", type_code="deduction", method_code="rule_based")
        ctx = _make_context("300000", [comp])
        lines = run_earnings_engine(ctx)
        self.assertEqual(len(lines), 0)


# ── Overtime Engine ───────────────────────────────────────────────────────────

class TestOvertimeEngine(unittest.TestCase):

    def _hourly(self, basic: str) -> Decimal:
        return _D(basic) / _D("173.33")

    def test_day_tier1_120pct(self):
        comp = _make_component(
            "OVERTIME_DAY_T1", method_code="hourly", input_quantity="8",
        )
        ctx = _make_context("300000", [comp], _cameroon_overtime_rule_sets())
        lines = run_overtime_engine(ctx)
        self.assertEqual(len(lines), 1)
        expected = (self._hourly("300000") * _D("8") * _D("1.20")).quantize(_D("0.0001"))
        self.assertEqual(lines[0].component_amount, expected)

    def test_day_tier2_130pct(self):
        comp = _make_component(
            "OVERTIME_DAY_T2", method_code="hourly", input_quantity="8",
        )
        ctx = _make_context("300000", [comp], _cameroon_overtime_rule_sets())
        lines = run_overtime_engine(ctx)
        self.assertEqual(len(lines), 1)
        expected = (self._hourly("300000") * _D("8") * _D("1.30")).quantize(_D("0.0001"))
        self.assertEqual(lines[0].component_amount, expected)

    def test_day_tier3_140pct(self):
        comp = _make_component(
            "OVERTIME_DAY_T3", method_code="hourly", input_quantity="4",
        )
        ctx = _make_context("300000", [comp], _cameroon_overtime_rule_sets())
        lines = run_overtime_engine(ctx)
        self.assertEqual(len(lines), 1)
        expected = (self._hourly("300000") * _D("4") * _D("1.40")).quantize(_D("0.0001"))
        self.assertEqual(lines[0].component_amount, expected)

    def test_night_150pct(self):
        comp = _make_component(
            "OVERTIME_NIGHT", method_code="hourly", input_quantity="10",
        )
        ctx = _make_context("300000", [comp], _cameroon_overtime_rule_sets())
        lines = run_overtime_engine(ctx)
        self.assertEqual(len(lines), 1)
        expected = (self._hourly("300000") * _D("10") * _D("1.50")).quantize(_D("0.0001"))
        self.assertEqual(lines[0].component_amount, expected)

    def test_legacy_overtime_standard_150pct(self):
        comp = _make_component(
            "OVERTIME", method_code="hourly", input_quantity="10",
        )
        ctx = _make_context("300000", [comp], _cameroon_overtime_rule_sets())
        lines = run_overtime_engine(ctx)
        self.assertEqual(len(lines), 1)
        expected = (self._hourly("300000") * _D("10") * _D("1.50")).quantize(_D("0.0001"))
        self.assertEqual(lines[0].component_amount, expected)

    def test_manual_amount_override(self):
        comp = _make_component(
            "OVERTIME_DAY_T1", method_code="hourly",
            input_amount="50000", input_quantity="8",
        )
        ctx = _make_context("300000", [comp], _cameroon_overtime_rule_sets())
        lines = run_overtime_engine(ctx)
        self.assertEqual(len(lines), 1)
        # input_amount takes precedence over input_quantity
        self.assertEqual(lines[0].component_amount, _D("50000.0000"))

    def test_no_input_skipped(self):
        comp = _make_component("OVERTIME_DAY_T1", method_code="hourly")
        ctx = _make_context("300000", [comp], _cameroon_overtime_rule_sets())
        lines = run_overtime_engine(ctx)
        self.assertEqual(len(lines), 0)

    def test_fallback_rate_when_no_rule_set(self):
        comp = _make_component(
            "OVERTIME_DAY_T1", method_code="hourly", input_quantity="8",
        )
        ctx = _make_context("300000", [comp])  # no rule sets
        lines = run_overtime_engine(ctx)
        self.assertEqual(len(lines), 1)
        # Falls back to 50% premium (150%)
        expected = (self._hourly("300000") * _D("8") * _D("1.50")).quantize(_D("0.0001"))
        self.assertEqual(lines[0].component_amount, expected)


# ── Benefits-in-Kind Engine ───────────────────────────────────────────────────

class TestBenefitsInKindEngine(unittest.TestCase):

    def test_housing_bik_fixed(self):
        comp = _make_component("HOUSING_BIK", base_amount="50000")
        ctx = _make_context("300000", [comp])
        lines = run_benefits_in_kind_engine(ctx)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].component_amount, _D("50000.0000"))

    def test_transport_bik_percentage(self):
        comp = _make_component(
            "TRANSPORT_BIK", method_code="percentage", base_rate="0.05",
        )
        ctx = _make_context("300000", [comp])
        lines = run_benefits_in_kind_engine(ctx)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].component_amount, _D("15000.0000"))

    def test_non_bik_code_skipped(self):
        comp = _make_component("BASE_SALARY", base_amount="300000")
        ctx = _make_context("300000", [comp])
        lines = run_benefits_in_kind_engine(ctx)
        self.assertEqual(len(lines), 0)

    def test_non_earning_type_skipped(self):
        comp = _make_component("HOUSING_BIK", type_code="deduction", base_amount="50000")
        ctx = _make_context("300000", [comp])
        lines = run_benefits_in_kind_engine(ctx)
        self.assertEqual(len(lines), 0)

    def test_zero_amount_skipped(self):
        comp = _make_component("HOUSING_BIK", base_amount="0")
        ctx = _make_context("300000", [comp])
        lines = run_benefits_in_kind_engine(ctx)
        self.assertEqual(len(lines), 0)


# ── CNPS Engine ───────────────────────────────────────────────────────────────

class TestCnpsEngine(unittest.TestCase):

    def _make_cnps_context(self, rule_sets: dict | None = None) -> EngineContext:
        comps = [
            _make_component("EMPLOYEE_CNPS", type_code="deduction", method_code="rule_based",
                            is_taxable=False, is_pensionable=False),
            _make_component("EMPLOYER_CNPS", type_code="employer_contribution", method_code="rule_based",
                            is_taxable=False, is_pensionable=False),
        ]
        return _make_context("300000", comps, rule_sets or _cameroon_cnps_rule_sets())

    def test_below_cap(self):
        ctx = self._make_cnps_context()
        lines = run_cnps_engine(ctx, _D("300000"))
        self.assertEqual(len(lines), 2)
        for line in lines:
            self.assertEqual(line.component_amount, _D("12600.0000"))

    def test_at_cap(self):
        ctx = self._make_cnps_context()
        lines = run_cnps_engine(ctx, _D("750000"))
        self.assertEqual(len(lines), 2)
        for line in lines:
            self.assertEqual(line.component_amount, _D("31500.0000"))

    def test_above_cap(self):
        ctx = self._make_cnps_context()
        lines = run_cnps_engine(ctx, _D("1000000"))
        self.assertEqual(len(lines), 2)
        for line in lines:
            # Capped at 750,000 base → 750,000 × 4.2 % = 31,500
            self.assertEqual(line.component_amount, _D("31500.0000"))

    def test_zero_base_no_lines(self):
        ctx = self._make_cnps_context()
        lines = run_cnps_engine(ctx, _D("0"))
        self.assertEqual(len(lines), 0)

    def test_fallback_rates_when_no_rule_sets(self):
        ctx = self._make_cnps_context(rule_sets={})
        lines = run_cnps_engine(ctx, _D("300000"))
        self.assertEqual(len(lines), 2)
        for line in lines:
            # Fallback: 4.2 % of 300,000 = 12,600
            self.assertEqual(line.component_amount, _D("12600.0000"))

    def test_fallback_cap_applies(self):
        ctx = self._make_cnps_context(rule_sets={})
        lines = run_cnps_engine(ctx, _D("1000000"))
        self.assertEqual(len(lines), 2)
        for line in lines:
            # Fallback cap is 750,000 → 750,000 × 4.2 % = 31,500
            self.assertEqual(line.component_amount, _D("31500.0000"))


# ── Salary Deductions Engine ─────────────────────────────────────────────────

class TestSalaryDeductionsEngine(unittest.TestCase):

    def _make_deduction_context(self, rule_sets: dict | None = None) -> EngineContext:
        comps = [
            _make_component("CFC_HLF", type_code="deduction", method_code="rule_based",
                            is_taxable=False, is_pensionable=False),
            _make_component("FNE_EMPLOYEE", type_code="deduction", method_code="rule_based",
                            is_taxable=False, is_pensionable=False),
        ]
        return _make_context("300000", comps, rule_sets or _cameroon_deduction_rule_sets())

    def test_cfc_and_fne_at_300k(self):
        ctx = self._make_deduction_context()
        lines = run_salary_deductions_engine(ctx, _D("300000"))
        self.assertEqual(len(lines), 2)
        for line in lines:
            self.assertEqual(line.component_amount, _D("3000.0000"))

    def test_zero_gross_no_lines(self):
        ctx = self._make_deduction_context()
        lines = run_salary_deductions_engine(ctx, _D("0"))
        self.assertEqual(len(lines), 0)

    def test_rate_from_rule_set_overrides(self):
        custom_rules = {
            "CCF_MAIN": _make_rule_set(
                "CCF_MAIN", "levy", "gross_salary",
                [_make_bracket("0", None, "2.00")],  # 2 % instead of 1 %
            ),
            "FNE_EMPLOYEE_MAIN": _make_rule_set(
                "FNE_EMPLOYEE_MAIN", "levy", "gross_salary",
                [_make_bracket("0", None, "1.50")],  # 1.5 % instead of 1 %
            ),
        }
        ctx = self._make_deduction_context(custom_rules)
        lines = run_salary_deductions_engine(ctx, _D("300000"))
        self.assertEqual(len(lines), 2)
        cfc = _line_by_code(lines, ctx, "CFC_HLF")
        fne = _line_by_code(lines, ctx, "FNE_EMPLOYEE")
        self.assertIsNotNone(cfc)
        self.assertIsNotNone(fne)
        self.assertEqual(cfc.component_amount, _D("6000.0000"))
        self.assertEqual(fne.component_amount, _D("4500.0000"))

    def test_fallback_rates_when_no_rule_sets(self):
        ctx = self._make_deduction_context(rule_sets={})
        lines = run_salary_deductions_engine(ctx, _D("300000"))
        self.assertEqual(len(lines), 2)
        for line in lines:
            # Fallback: 1 % of 300,000 = 3,000
            self.assertEqual(line.component_amount, _D("3000.0000"))


# ── TDL Engine ────────────────────────────────────────────────────────────────

class TestTdlEngine(unittest.TestCase):

    def _make_tdl_context(self) -> EngineContext:
        comp = _make_component("TDL", type_code="tax", method_code="rule_based",
                               is_taxable=False, is_pensionable=False)
        return _make_context("300000", [comp], _cameroon_irpp_rule_sets())

    def test_below_50k_exempt(self):
        ctx = self._make_tdl_context()
        lines = run_tdl_engine(ctx, _D("40000"))
        self.assertEqual(len(lines), 0)

    def test_bracket_2_at_100k(self):
        ctx = self._make_tdl_context()
        lines = run_tdl_engine(ctx, _D("100000"))
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].component_amount, _D("167.0000"))

    def test_bracket_3_at_300k(self):
        ctx = self._make_tdl_context()
        lines = run_tdl_engine(ctx, _D("300000"))
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].component_amount, _D("250.0000"))

    def test_boundary_50k_is_exempt(self):
        """50,000 XAF is ≤ the lower_bound of bracket 2, so still in bracket 1 (exempt)."""
        ctx = self._make_tdl_context()
        lines = run_tdl_engine(ctx, _D("50000"))
        self.assertEqual(len(lines), 0)

    def test_just_above_50k(self):
        ctx = self._make_tdl_context()
        lines = run_tdl_engine(ctx, _D("50001"))
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].component_amount, _D("167.0000"))

    def test_zero_base_no_lines(self):
        ctx = self._make_tdl_context()
        lines = run_tdl_engine(ctx, _D("0"))
        self.assertEqual(len(lines), 0)


# ── IRPP Engine ───────────────────────────────────────────────────────────────

class TestIrppEngine(unittest.TestCase):

    def _make_irpp_context(
        self,
        number_of_parts: str = "1",
        extra_components: list[ComponentInput] | None = None,
    ) -> EngineContext:
        comps: list[ComponentInput] = [
            _make_component("IRPP", type_code="tax", method_code="rule_based",
                            is_taxable=False, is_pensionable=False),
            _make_component("CAC", type_code="tax", method_code="rule_based",
                            is_taxable=False, is_pensionable=False, base_rate="0.10"),
            _make_component("CRTV", type_code="deduction", method_code="rule_based",
                            is_taxable=False, is_pensionable=False),
        ]
        if extra_components:
            comps.extend(extra_components)
        return _make_context("300000", comps, _cameroon_irpp_rule_sets(), number_of_parts)

    def test_irpp_bracket_1_only(self):
        """150,000 monthly net imposable → annual 1,800,000 → all in bracket 1 (10%)."""
        ctx = self._make_irpp_context()
        lines = run_irpp_engine(ctx, _D("150000"), _D("300000"))
        irpp = _line_by_code(lines, ctx, "IRPP")
        self.assertIsNotNone(irpp)
        # 150,000 × 12 = 1,800,000 annual → 1,800,000 × 10 % = 180,000 → / 12 = 15,000
        self.assertEqual(irpp.component_amount, _D("15000.0000"))

    def test_irpp_crosses_bracket_2(self):
        """250,000 monthly → annual 3,000,000 → bracket 1 + bracket 2."""
        ctx = self._make_irpp_context()
        lines = run_irpp_engine(ctx, _D("250000"), _D("500000"))
        irpp = _line_by_code(lines, ctx, "IRPP")
        self.assertIsNotNone(irpp)
        # bracket 1: 2,000,000 × 10 % = 200,000
        # bracket 2: 1,000,000 × 15 % = 150,000
        # total annual = 350,000 → monthly = 29,166.6667
        self.assertEqual(irpp.component_amount, _D("29166.6667"))

    def test_irpp_crosses_bracket_3(self):
        """416,666.6667 monthly → annual 5,000,000 → brackets 1+2+3."""
        ctx = self._make_irpp_context()
        base = _D("5000000") / _D("12")
        lines = run_irpp_engine(ctx, base, _D("700000"))
        irpp = _line_by_code(lines, ctx, "IRPP")
        self.assertIsNotNone(irpp)
        # bracket 1: 2M × 10 % = 200K
        # bracket 2: 1M × 15 % = 150K
        # bracket 3: 2M × 25 % = 500K
        # total annual = 850K → monthly = 70,833.3333
        self.assertEqual(irpp.component_amount, _D("70833.3333"))

    def test_quotient_familial_2_parts_bracket_1(self):
        """With 2 parts, income is halved for bracket lookup then doubled back."""
        ctx = self._make_irpp_context("2")
        # 150,000 monthly → 1,800,000 annual → per part 900,000 → 10 % = 90,000
        # × 2 parts = 180,000 annual → 15,000/month (same as 1 part when fully in bracket 1)
        lines = run_irpp_engine(ctx, _D("150000"), _D("300000"))
        irpp = _line_by_code(lines, ctx, "IRPP")
        self.assertIsNotNone(irpp)
        self.assertEqual(irpp.component_amount, _D("15000.0000"))

    def test_quotient_familial_2_parts_reduces_tax(self):
        """With 2 parts on higher income, tax is reduced."""
        ctx = self._make_irpp_context("2")
        # 250,000 monthly → 3,000,000 annual → per part 1,500,000
        # per part: 1,500,000 × 10 % = 150,000
        # × 2 = 300,000 annual → 25,000/month
        lines = run_irpp_engine(ctx, _D("250000"), _D("500000"))
        irpp = _line_by_code(lines, ctx, "IRPP")
        self.assertIsNotNone(irpp)
        self.assertEqual(irpp.component_amount, _D("25000.0000"))

    def test_quotient_familial_2_5_parts(self):
        """Fractional parts work correctly."""
        ctx = self._make_irpp_context("2.5")
        # 250,000 monthly → 3,000,000 annual → per part 1,200,000
        # per part: 1,200,000 × 10 % = 120,000
        # × 2.5 = 300,000 annual → 25,000/month
        lines = run_irpp_engine(ctx, _D("250000"), _D("500000"))
        irpp = _line_by_code(lines, ctx, "IRPP")
        self.assertIsNotNone(irpp)
        self.assertEqual(irpp.component_amount, _D("25000.0000"))

    def test_cac_10pct_of_irpp(self):
        ctx = self._make_irpp_context()
        lines = run_irpp_engine(ctx, _D("150000"), _D("300000"))
        irpp = _line_by_code(lines, ctx, "IRPP")
        cac = _line_by_code(lines, ctx, "CAC")
        self.assertIsNotNone(irpp)
        self.assertIsNotNone(cac)
        expected_cac = (irpp.component_amount * _D("0.10")).quantize(_D("0.0001"))
        self.assertEqual(cac.component_amount, expected_cac)

    def test_crtv_bracket_lookup_300k(self):
        ctx = self._make_irpp_context()
        lines = run_irpp_engine(ctx, _D("150000"), _D("300000"))
        crtv = _line_by_code(lines, ctx, "CRTV")
        self.assertIsNotNone(crtv)
        # 300,000 exactly = upper bound of bracket 4 (200K–300K) → upper-inclusive → 3,250
        self.assertEqual(crtv.component_amount, _D("3250.0000"))

    def test_crtv_upper_inclusive_100k(self):
        """100,000 exactly sits at upper bound of bracket 2 → stays in bracket 2."""
        ctx = self._make_irpp_context()
        lines = run_irpp_engine(ctx, _D("50000"), _D("100000"))
        crtv = _line_by_code(lines, ctx, "CRTV")
        self.assertIsNotNone(crtv)
        self.assertEqual(crtv.component_amount, _D("750.0000"))

    def test_crtv_above_1m(self):
        ctx = self._make_irpp_context()
        lines = run_irpp_engine(ctx, _D("400000"), _D("1500000"))
        crtv = _line_by_code(lines, ctx, "CRTV")
        self.assertIsNotNone(crtv)
        self.assertEqual(crtv.component_amount, _D("13000.0000"))

    def test_zero_taxable_base_still_produces_crtv(self):
        ctx = self._make_irpp_context()
        lines = run_irpp_engine(ctx, _D("0"), _D("300000"))
        irpp = _line_by_code(lines, ctx, "IRPP")
        crtv = _line_by_code(lines, ctx, "CRTV")
        self.assertIsNone(irpp)  # Zero base → no IRPP
        self.assertIsNotNone(crtv)
        # 300K → bracket 4 upper-inclusive → 3,250
        self.assertEqual(crtv.component_amount, _D("3250.0000"))

    def test_crtv_below_50k_exempt(self):
        ctx = self._make_irpp_context()
        lines = run_irpp_engine(ctx, _D("0"), _D("30000"))
        crtv = _line_by_code(lines, ctx, "CRTV")
        self.assertIsNone(crtv)  # 0 CRTV → no line produced


# ── Employer Contribution Engine ──────────────────────────────────────────────

class TestEmployerContributionEngine(unittest.TestCase):

    def _make_employer_context(self, rule_sets: dict | None = None) -> EngineContext:
        comps = [
            _make_component("FNE", type_code="employer_contribution", method_code="rule_based",
                            is_taxable=False, is_pensionable=False),
            _make_component("EMPLOYER_AF", type_code="employer_contribution", method_code="rule_based",
                            is_taxable=False, is_pensionable=False),
            _make_component("ACCIDENT_RISK_EMPLOYER", type_code="employer_contribution", method_code="rule_based",
                            is_taxable=False, is_pensionable=False),
            _make_component("EMPLOYER_CNPS", type_code="employer_contribution", method_code="rule_based",
                            is_taxable=False, is_pensionable=False),
        ]
        return _make_context("300000", comps, rule_sets or _cameroon_employer_rule_sets())

    def test_fne_employer_2_5pct(self):
        ctx = self._make_employer_context()
        lines = run_employer_contribution_engine(ctx, _D("300000"))
        fne = _line_by_code(lines, ctx, "FNE")
        self.assertIsNotNone(fne)
        self.assertEqual(fne.component_amount, _D("7500.0000"))

    def test_fne_employer_fallback_rate(self):
        ctx = self._make_employer_context(rule_sets={})
        lines = run_employer_contribution_engine(ctx, _D("300000"))
        fne = _line_by_code(lines, ctx, "FNE")
        self.assertIsNotNone(fne)
        # Fallback: 2.5 % of 300,000 = 7,500
        self.assertEqual(fne.component_amount, _D("7500.0000"))

    def test_af_general_regime_7pct(self):
        ctx = self._make_employer_context()
        lines = run_employer_contribution_engine(ctx, _D("300000"))
        af = _line_by_code(lines, ctx, "EMPLOYER_AF")
        self.assertIsNotNone(af)
        self.assertEqual(af.component_amount, _D("21000.0000"))

    def test_af_capped_at_ceiling(self):
        ctx = self._make_employer_context()
        lines = run_employer_contribution_engine(ctx, _D("1000000"))
        af = _line_by_code(lines, ctx, "EMPLOYER_AF")
        self.assertIsNotNone(af)
        # 1,000,000 × 7 % = 70,000 but cap = 52,500
        self.assertEqual(af.component_amount, _D("52500"))

    def test_accident_risk_group_a(self):
        ctx = self._make_employer_context()
        lines = run_employer_contribution_engine(ctx, _D("300000"))
        ar = _line_by_code(lines, ctx, "ACCIDENT_RISK_EMPLOYER")
        self.assertIsNotNone(ar)
        self.assertEqual(ar.component_amount, _D("5250.0000"))

    def test_zero_gross_no_lines(self):
        ctx = self._make_employer_context()
        lines = run_employer_contribution_engine(ctx, _D("0"))
        self.assertEqual(len(lines), 0)

    def test_employer_cnps_skipped(self):
        """EMPLOYER_CNPS is handled by the CNPS engine, not this engine."""
        ctx = self._make_employer_context()
        lines = run_employer_contribution_engine(ctx, _D("300000"))
        cnps = _line_by_code(lines, ctx, "EMPLOYER_CNPS")
        self.assertIsNone(cnps)

    def test_all_three_contributions_present(self):
        ctx = self._make_employer_context()
        lines = run_employer_contribution_engine(ctx, _D("300000"))
        # Should have FNE, AF, and Accident Risk (not CNPS)
        self.assertEqual(len(lines), 3)


if __name__ == "__main__":
    unittest.main()
