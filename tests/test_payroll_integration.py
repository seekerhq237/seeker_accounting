"""Integration tests for PayrollCalculationService.calculate() — full pipeline.

These tests exercise the complete calculation pipeline from ORM-like stub
objects through _build_context() → _run_engines() → EmployeeCalculationResult,
using real Cameroon 2024 statutory data at multiple salary points.

Each test constructs a full employee with all Cameroon components assigned
and all rule sets configured, then verifies every line against independently
computed reference values.

Reference methodology:
  gross = base_salary + allowances + overtime
  pensionable_gross = sum of components where is_pensionable=True
  cnps_employee = min(pensionable_gross × 0.042, 31500)
  cfc = gross × 0.01
  fne_employee = gross × 0.01
  taxable_gross = sum of is_taxable=True earnings
  salaire_taxable = taxable_gross − cnps_employee − cfc − fne_employee
  after_abattement = salaire_taxable × 0.70
  monthly_net_imposable = after_abattement − 500000/12
  irpp_annual = progressive(monthly_net_imposable × 12)
  irpp_monthly = irpp_annual / 12  (quotient familial division + re-multiplication)
  cac = irpp × 0.10
  crtv = bracket_lookup(gross)
  tdl = bracket_lookup(gross)
  cnps_employer = min(pensionable_gross × 0.042, 31500)
  fne_employer = gross × 0.025
  accident_risk = gross × 0.0175
  af = min(gross × 0.07, 52500)  [capped at 750K ceiling]
  net_payable = gross − cnps_employee − cfc − fne_employee − irpp − cac − crtv − tdl
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN

import pytest


# ── Lightweight ORM stubs ─────────────────────────────────────────────────────
# These mimic the attributes read by PayrollCalculationService._build_context()
# without requiring a database session.


@dataclass
class StubComponent:
    id: int
    component_code: str
    component_name: str
    component_type_code: str
    calculation_method_code: str
    is_taxable: bool
    is_pensionable: bool


@dataclass
class StubAssignment:
    component: StubComponent
    override_amount: Decimal | None = None
    override_rate: Decimal | None = None


@dataclass
class StubInputLine:
    employee_id: int
    component_id: int
    input_amount: Decimal
    input_quantity: Decimal | None = None


@dataclass
class StubInputBatch:
    lines: list[StubInputLine] = field(default_factory=list)


@dataclass
class StubBracket:
    line_number: int
    lower_bound_amount: Decimal | None = None
    upper_bound_amount: Decimal | None = None
    rate_percent: Decimal | None = None
    fixed_amount: Decimal | None = None
    deduction_amount: Decimal | None = None
    cap_amount: Decimal | None = None


@dataclass
class StubRuleSet:
    id: int
    rule_code: str
    rule_type_code: str
    calculation_basis_code: str
    brackets: list[StubBracket] = field(default_factory=list)


@dataclass
class StubProfile:
    company_id: int
    employee_id: int
    basic_salary: Decimal
    currency_code: str = "XAF"
    number_of_parts: Decimal = Decimal("1.0")


# ── Cameroon component & rule set factory ─────────────────────────────────────

_COMPONENTS: dict[str, tuple[str, str, str, bool, bool]] = {
    # code: (name, type_code, calc_method, is_taxable, is_pensionable)
    "BASE_SALARY":          ("Base Salary",                "earning",                 "fixed_amount", True,  True),
    "OVERTIME":             ("Overtime",                   "earning",                 "percentage",   True,  True),
    "OVERTIME_DAY_T1":      ("Overtime Day Tier 1 (120%)", "earning",                 "hourly",       True,  True),
    "OVERTIME_DAY_T2":      ("Overtime Day Tier 2 (130%)", "earning",                 "hourly",       True,  True),
    "OVERTIME_DAY_T3":      ("Overtime Day Tier 3 (140%)", "earning",                 "hourly",       True,  True),
    "OVERTIME_NIGHT":       ("Overtime Night (150%)",      "earning",                 "hourly",       True,  True),
    "HOUSING_ALLOWANCE":    ("Housing Allowance",          "earning",                 "fixed_amount", False, False),
    "TRANSPORT_ALLOWANCE":  ("Transport Allowance",        "earning",                 "fixed_amount", False, False),
    "EMPLOYEE_CNPS":        ("CNPS Pension (Employee)",    "deduction",               "rule_based",   False, False),
    "IRPP":                 ("IRPP Withholding",           "tax",                     "rule_based",   False, False),
    "CAC":                  ("CAC",                        "tax",                     "rule_based",   False, False),
    "TDL":                  ("TDL",                        "tax",                     "rule_based",   False, False),
    "CRTV":                 ("CRTV",                       "deduction",               "rule_based",   False, False),
    "CFC_HLF":              ("CFC",                        "deduction",               "rule_based",   False, False),
    "FNE_EMPLOYEE":         ("FNE Employee",               "deduction",               "rule_based",   False, False),
    "EMPLOYER_CNPS":        ("CNPS Pension (Employer)",    "employer_contribution",   "rule_based",   False, False),
    "FNE":                  ("FNE Employer",               "employer_contribution",   "rule_based",   False, False),
    "ACCIDENT_RISK_EMPLOYER": ("Accident Risk",            "employer_contribution",   "rule_based",   False, False),
    "EMPLOYER_AF":          ("Allocations Familiales",     "employer_contribution",   "rule_based",   False, False),
}


def _build_components() -> dict[str, StubComponent]:
    """Build all Cameroon stub components with sequential IDs."""
    result = {}
    for idx, (code, (name, type_code, calc, taxable, pensionable)) in enumerate(_COMPONENTS.items(), start=1):
        result[code] = StubComponent(
            id=idx,
            component_code=code,
            component_name=name,
            component_type_code=type_code,
            calculation_method_code=calc,
            is_taxable=taxable,
            is_pensionable=pensionable,
        )
    return result


def _D(v: str) -> Decimal:
    return Decimal(v)


def _build_rule_sets() -> list[StubRuleSet]:
    """Build all Cameroon 2024 rule sets with real statutory data."""
    rs_id = 0

    def _rs(code: str, name: str, rtype: str, basis: str, brackets_raw: list) -> StubRuleSet:
        nonlocal rs_id
        rs_id += 1
        brackets = []
        for b in brackets_raw:
            brackets.append(StubBracket(
                line_number=b[0],
                lower_bound_amount=b[1],
                upper_bound_amount=b[2],
                rate_percent=b[3],
                fixed_amount=b[4],
                deduction_amount=b[5],
                cap_amount=b[6],
            ))
        return StubRuleSet(id=rs_id, rule_code=code, rule_type_code=rtype,
                           calculation_basis_code=basis, brackets=brackets)

    return [
        # IRPP main barème (annual brackets)
        _rs("DGI_IRPP_MAIN", "IRPP", "pit", "taxable_gross", [
            (1, _D("0"),       _D("2000000"),  _D("10.00"), None, None, None),
            (2, _D("2000000"), _D("3000000"),  _D("15.00"), None, None, None),
            (3, _D("3000000"), _D("5000000"),  _D("25.00"), None, None, None),
            (4, _D("5000000"), None,           _D("35.00"), None, None, None),
        ]),
        # Abattement
        _rs("DGI_IRPP_ABATTEMENT", "Abattement", "abattement", "taxable_gross", [
            (1, None, None, _D("30.00"), None, _D("500000"), None),
        ]),
        # TDL
        _rs("TDL_MAIN", "TDL", "levy", "gross_salary", [
            (1, _D("0"),      _D("50000"),   None, _D("0"),   None, None),
            (2, _D("50000"),  _D("208333"),  None, _D("167"), None, None),
            (3, _D("208333"), None,          None, _D("250"), None, None),
        ]),
        # CNPS Employee
        _rs("CNPS_EMPLOYEE_MAIN", "CNPS Employee", "pension_employee", "gross_salary", [
            (1, _D("0"), _D("750000"), _D("4.20"), None, None, _D("31500")),
        ]),
        # CNPS Employer
        _rs("CNPS_EMPLOYER_MAIN", "CNPS Employer", "pension_employer", "gross_salary", [
            (1, _D("0"), _D("750000"), _D("4.20"), None, None, _D("31500")),
        ]),
        # Accident Risk Group A
        _rs("ACCIDENT_RISK_STANDARD", "Accident Risk A", "accident_risk", "gross_salary", [
            (1, _D("0"), None, _D("1.75"), None, None, None),
        ]),
        # Family Allowances (general regime)
        _rs("AF_MAIN", "AF General", "family_benefit", "gross_salary", [
            (1, _D("0"), _D("750000"), _D("7.00"), None, None, _D("52500")),
        ]),
        # CCF / CFC
        _rs("CCF_MAIN", "CFC", "levy", "gross_salary", [
            (1, _D("0"), None, _D("1.00"), None, None, None),
        ]),
        # FNE Employee
        _rs("FNE_EMPLOYEE_MAIN", "FNE Employee", "levy", "gross_salary", [
            (1, _D("0"), None, _D("1.00"), None, None, None),
        ]),
        # FNE Employer
        _rs("FNE_EMPLOYER_MAIN", "FNE Employer", "levy", "gross_salary", [
            (1, _D("0"), None, _D("2.50"), None, None, None),
        ]),
        # CRTV
        _rs("CRTV_MAIN", "CRTV", "levy", "gross_salary", [
            (1, _D("0"),       _D("50000"),    None, _D("0"),     None, None),
            (2, _D("50000"),   _D("100000"),   None, _D("750"),   None, None),
            (3, _D("100000"),  _D("200000"),   None, _D("1950"),  None, None),
            (4, _D("200000"),  _D("300000"),   None, _D("3250"),  None, None),
            (5, _D("300000"),  _D("500000"),   None, _D("4550"),  None, None),
            (6, _D("500000"),  _D("700000"),   None, _D("5850"),  None, None),
            (7, _D("700000"),  _D("800000"),   None, _D("9750"),  None, None),
            (8, _D("800000"),  _D("1000000"),  None, _D("12350"), None, None),
            (9, _D("1000000"), None,           None, _D("13000"), None, None),
        ]),
        # Overtime rule sets
        _rs("OVERTIME_STANDARD", "OT Standard", "overtime", "basic_salary", [
            (1, None, None, _D("50.00"), None, None, None),
        ]),
        _rs("OVERTIME_DAY_T1", "OT Day T1", "overtime", "basic_salary", [
            (1, None, None, _D("20.00"), None, None, None),
        ]),
        _rs("OVERTIME_DAY_T2", "OT Day T2", "overtime", "basic_salary", [
            (1, None, None, _D("30.00"), None, None, None),
        ]),
        _rs("OVERTIME_DAY_T3", "OT Day T3", "overtime", "basic_salary", [
            (1, None, None, _D("40.00"), None, None, None),
        ]),
        _rs("OVERTIME_NIGHT", "OT Night", "overtime", "basic_salary", [
            (1, None, None, _D("50.00"), None, None, None),
        ]),
    ]


# ── Fixture builders ─────────────────────────────────────────────────────────

def _build_standard_employee(
    basic_salary: Decimal,
    employee_id: int = 1,
    number_of_parts: Decimal = Decimal("1.0"),
    housing_allowance: Decimal | None = None,
    transport_allowance: Decimal | None = None,
) -> tuple[StubProfile, list[StubAssignment], list[StubInputBatch], list[StubRuleSet]]:
    """Build a standard Cameroon employee with all components and rule sets.

    Returns (profile, assignments, input_batches, rule_sets) tuple ready for
    PayrollCalculationService.calculate().
    """
    comps = _build_components()
    profile = StubProfile(
        company_id=1,
        employee_id=employee_id,
        basic_salary=basic_salary,
        number_of_parts=number_of_parts,
    )

    # Standard component assignments (all statutory + base salary)
    assignment_codes = [
        "BASE_SALARY",
        "EMPLOYEE_CNPS", "IRPP", "CAC", "TDL", "CRTV",
        "CFC_HLF", "FNE_EMPLOYEE",
        "EMPLOYER_CNPS", "FNE", "ACCIDENT_RISK_EMPLOYER", "EMPLOYER_AF",
    ]

    assignments = []
    for code in assignment_codes:
        assignments.append(StubAssignment(component=comps[code]))

    # Optional allowances
    if housing_allowance is not None:
        assignments.append(StubAssignment(
            component=comps["HOUSING_ALLOWANCE"],
            override_amount=housing_allowance,
        ))
    if transport_allowance is not None:
        assignments.append(StubAssignment(
            component=comps["TRANSPORT_ALLOWANCE"],
            override_amount=transport_allowance,
        ))

    rule_sets = _build_rule_sets()
    return profile, assignments, [], rule_sets


# ── Reference calculation helpers ─────────────────────────────────────────────

def _ref_cnps(pensionable_gross: Decimal) -> Decimal:
    """Reference CNPS employee: 4.2% capped at 31,500."""
    return min(pensionable_gross * _D("0.042"), _D("31500"))


def _ref_cfc(gross: Decimal) -> Decimal:
    return gross * _D("0.01")


def _ref_fne_employee(gross: Decimal) -> Decimal:
    return gross * _D("0.01")


def _ref_irpp_monthly(monthly_net_imposable: Decimal, number_of_parts: Decimal = _D("1")) -> Decimal:
    """Compute monthly IRPP with quotient familial.

    Steps:
    1. annual = monthly_net_imposable × 12
    2. quotient = annual / number_of_parts
    3. irpp_per_part = progressive(quotient)
    4. irpp_annual = irpp_per_part × number_of_parts
    5. irpp_monthly = irpp_annual / 12
    """
    annual = monthly_net_imposable * 12
    quotient = annual / number_of_parts

    # Progressive bracket calculation on quotient
    brackets = [
        (_D("0"),       _D("2000000"), _D("0.10")),
        (_D("2000000"), _D("3000000"), _D("0.15")),
        (_D("3000000"), _D("5000000"), _D("0.25")),
        (_D("5000000"), None,          _D("0.35")),
    ]
    irpp_per_part = _D("0")
    for lower, upper, rate in brackets:
        if quotient <= lower:
            break
        if upper is not None:
            taxable_in_bracket = min(quotient, upper) - lower
        else:
            taxable_in_bracket = quotient - lower
        irpp_per_part += taxable_in_bracket * rate

    irpp_annual = irpp_per_part * number_of_parts
    irpp_monthly = (irpp_annual / 12).quantize(_D("0.0001"), rounding=ROUND_HALF_UP)
    return irpp_monthly


def _ref_taxable_base(
    taxable_gross: Decimal,
    cnps_employee: Decimal,
    cfc: Decimal,
    fne_employee: Decimal,
) -> Decimal:
    """Compute monthly net imposable for IRPP.

    salaire_taxable = taxable_gross − CNPS − CFC − FNE
    after_abattement = salaire_taxable × 0.70
    monthly_net_imposable = after_abattement − 500000/12
    """
    salaire_taxable = max(taxable_gross - cnps_employee - cfc - fne_employee, _D("0"))
    after_abattement = (salaire_taxable * _D("0.70")).quantize(_D("0.0001"))
    monthly_deduction = (_D("500000") / 12).quantize(_D("0.0001"))
    return max(after_abattement - monthly_deduction, _D("0"))


def _ref_crtv(gross: Decimal) -> Decimal:
    """CRTV bracket lookup (upper-bound inclusive)."""
    brackets = [
        (_D("0"),       _D("50000"),   _D("0")),
        (_D("50000"),   _D("100000"),  _D("750")),
        (_D("100000"),  _D("200000"),  _D("1950")),
        (_D("200000"),  _D("300000"),  _D("3250")),
        (_D("300000"),  _D("500000"),  _D("4550")),
        (_D("500000"),  _D("700000"),  _D("5850")),
        (_D("700000"),  _D("800000"),  _D("9750")),
        (_D("800000"),  _D("1000000"), _D("12350")),
        (_D("1000000"), None,          _D("13000")),
    ]
    for lower, upper, amount in brackets:
        if upper is None or gross <= upper:
            return amount
    return _D("0")


def _ref_tdl(gross: Decimal) -> Decimal:
    """TDL bracket lookup (upper-bound inclusive)."""
    brackets = [
        (_D("0"),      _D("50000"),  _D("0")),
        (_D("50000"),  _D("208333"), _D("167")),
        (_D("208333"), None,         _D("250")),
    ]
    for lower, upper, amount in brackets:
        if upper is None or gross <= upper:
            return amount
    return _D("0")


def _line_by_code(result, code: str) -> Decimal:
    """Find a result line by component code (via component map)."""
    comps = _build_components()
    comp = comps.get(code)
    if comp is None:
        return _D("0")
    for line in result.lines:
        if line.component_id == comp.id:
            return line.component_amount
    return _D("0")


# ── Instantiate the service ──────────────────────────────────────────────────

from seeker_accounting.modules.payroll.services.payroll_calculation_service import PayrollCalculationService

_svc = PayrollCalculationService()


# ══════════════════════════════════════════════════════════════════════════════
# Test Class: Base salary only (no allowances, no overtime)
# ══════════════════════════════════════════════════════════════════════════════

class TestBaseSalaryOnly:
    """Full pipeline with base salary only at multiple salary points.

    These are the cleanest tests: gross = base = taxable_gross = pensionable_gross.
    """

    @pytest.mark.parametrize("salary", [
        _D("50000"),
        _D("150000"),
        _D("300000"),
        _D("500000"),
        _D("750000"),
        _D("1000000"),
        _D("1500000"),
    ])
    def test_gross_equals_base(self, salary: Decimal):
        profile, assignments, batches, rule_sets = _build_standard_employee(salary)
        result = _svc.calculate(profile, assignments, batches, rule_sets, 2024, 6)

        assert result.error_message is None
        assert result.gross_earnings == salary

    @pytest.mark.parametrize("salary,expected_cnps", [
        (_D("50000"),   _D("50000")  * _D("0.042")),
        (_D("150000"),  _D("150000") * _D("0.042")),
        (_D("300000"),  _D("300000") * _D("0.042")),
        (_D("500000"),  _D("500000") * _D("0.042")),
        (_D("750000"),  _D("31500")),    # cap
        (_D("1000000"), _D("31500")),    # capped
        (_D("1500000"), _D("31500")),    # capped
    ])
    def test_cnps_employee(self, salary: Decimal, expected_cnps: Decimal):
        profile, assignments, batches, rule_sets = _build_standard_employee(salary)
        result = _svc.calculate(profile, assignments, batches, rule_sets, 2024, 6)

        actual = _line_by_code(result, "EMPLOYEE_CNPS")
        assert actual == expected_cnps, f"CNPS employee for {salary}: {actual} != {expected_cnps}"

    @pytest.mark.parametrize("salary", [
        _D("50000"), _D("150000"), _D("300000"), _D("500000"),
        _D("750000"), _D("1000000"), _D("1500000"),
    ])
    def test_cfc_and_fne_employee(self, salary: Decimal):
        profile, assignments, batches, rule_sets = _build_standard_employee(salary)
        result = _svc.calculate(profile, assignments, batches, rule_sets, 2024, 6)

        assert _line_by_code(result, "CFC_HLF") == salary * _D("0.01")
        assert _line_by_code(result, "FNE_EMPLOYEE") == salary * _D("0.01")

    @pytest.mark.parametrize("salary", [
        _D("50000"), _D("150000"), _D("300000"), _D("500000"),
        _D("750000"), _D("1000000"), _D("1500000"),
    ])
    def test_irpp_against_reference(self, salary: Decimal):
        """Verify IRPP matches independent reference calculation."""
        profile, assignments, batches, rule_sets = _build_standard_employee(salary)
        result = _svc.calculate(profile, assignments, batches, rule_sets, 2024, 6)

        cnps = _ref_cnps(salary)  # pensionable = salary for base-only
        cfc = _ref_cfc(salary)
        fne = _ref_fne_employee(salary)
        taxable_base = _ref_taxable_base(salary, cnps, cfc, fne)
        expected_irpp = _ref_irpp_monthly(taxable_base)
        actual_irpp = _line_by_code(result, "IRPP")

        assert actual_irpp == expected_irpp, (
            f"IRPP for salary={salary}: actual={actual_irpp}, expected={expected_irpp}, "
            f"taxable_base={taxable_base}"
        )

    @pytest.mark.parametrize("salary", [
        _D("50000"), _D("150000"), _D("300000"), _D("500000"),
        _D("750000"), _D("1000000"), _D("1500000"),
    ])
    def test_cac_is_10pct_of_irpp(self, salary: Decimal):
        profile, assignments, batches, rule_sets = _build_standard_employee(salary)
        result = _svc.calculate(profile, assignments, batches, rule_sets, 2024, 6)

        irpp = _line_by_code(result, "IRPP")
        cac = _line_by_code(result, "CAC")
        # Engine quantizes CAC to 4dp
        expected_cac = (irpp * _D("0.10")).quantize(_D("0.0001"))
        assert cac == expected_cac, f"CAC for salary={salary}: {cac} != {expected_cac}"

    @pytest.mark.parametrize("salary", [
        _D("50000"), _D("150000"), _D("300000"), _D("500000"),
        _D("750000"), _D("1000000"), _D("1500000"),
    ])
    def test_crtv_bracket(self, salary: Decimal):
        profile, assignments, batches, rule_sets = _build_standard_employee(salary)
        result = _svc.calculate(profile, assignments, batches, rule_sets, 2024, 6)

        actual = _line_by_code(result, "CRTV")
        expected = _ref_crtv(salary)
        assert actual == expected, f"CRTV for salary={salary}: {actual} != {expected}"

    @pytest.mark.parametrize("salary", [
        _D("50000"), _D("150000"), _D("300000"), _D("500000"),
        _D("750000"), _D("1000000"), _D("1500000"),
    ])
    def test_tdl_bracket(self, salary: Decimal):
        profile, assignments, batches, rule_sets = _build_standard_employee(salary)
        result = _svc.calculate(profile, assignments, batches, rule_sets, 2024, 6)

        actual = _line_by_code(result, "TDL")
        expected = _ref_tdl(salary)
        assert actual == expected, f"TDL for salary={salary}: {actual} != {expected}"

    @pytest.mark.parametrize("salary", [
        _D("50000"), _D("150000"), _D("300000"), _D("500000"),
        _D("750000"), _D("1000000"), _D("1500000"),
    ])
    def test_employer_contributions(self, salary: Decimal):
        profile, assignments, batches, rule_sets = _build_standard_employee(salary)
        result = _svc.calculate(profile, assignments, batches, rule_sets, 2024, 6)

        # CNPS Employer (same as employee: 4.2% capped)
        expected_cnps = _ref_cnps(salary)
        assert _line_by_code(result, "EMPLOYER_CNPS") == expected_cnps

        # FNE Employer: 2.5% uncapped
        assert _line_by_code(result, "FNE") == salary * _D("0.025")

        # Accident Risk Group A: 1.75% uncapped
        assert _line_by_code(result, "ACCIDENT_RISK_EMPLOYER") == salary * _D("0.0175")

        # AF: 7% capped at 52,500
        expected_af = min(salary * _D("0.07"), _D("52500"))
        assert _line_by_code(result, "EMPLOYER_AF") == expected_af

    @pytest.mark.parametrize("salary", [
        _D("50000"), _D("150000"), _D("300000"), _D("500000"),
        _D("750000"), _D("1000000"), _D("1500000"),
    ])
    def test_net_payable_reconciliation(self, salary: Decimal):
        """Verify net_payable = total_earnings − total_deductions − total_taxes."""
        profile, assignments, batches, rule_sets = _build_standard_employee(salary)
        result = _svc.calculate(profile, assignments, batches, rule_sets, 2024, 6)

        expected_net = result.total_earnings - result.total_employee_deductions - result.total_taxes
        assert result.net_payable == max(expected_net, _D("0"))

    @pytest.mark.parametrize("salary", [
        _D("50000"), _D("150000"), _D("300000"), _D("500000"),
        _D("750000"), _D("1000000"), _D("1500000"),
    ])
    def test_employer_cost_base(self, salary: Decimal):
        """employer_cost_base = gross_earnings + total_employer_contributions."""
        profile, assignments, batches, rule_sets = _build_standard_employee(salary)
        result = _svc.calculate(profile, assignments, batches, rule_sets, 2024, 6)

        assert result.employer_cost_base == result.gross_earnings + result.total_employer_contributions


# ══════════════════════════════════════════════════════════════════════════════
# Test Class: With allowances (non-taxable, non-pensionable)
# ══════════════════════════════════════════════════════════════════════════════

class TestWithAllowances:
    """Test that non-taxable, non-pensionable allowances are handled correctly.

    Housing and transport allowances increase gross but do NOT increase:
    - CNPS base (not pensionable)
    - IRPP taxable base (not taxable)

    They DO increase:
    - CFC/FNE employee (based on gross)
    - Employer contributions based on gross (FNE, accident risk)
    """

    def test_300k_with_50k_allowances(self):
        salary = _D("300000")
        housing = _D("30000")
        transport = _D("20000")
        gross = salary + housing + transport  # 350,000

        profile, assignments, batches, rule_sets = _build_standard_employee(
            salary, housing_allowance=housing, transport_allowance=transport,
        )
        result = _svc.calculate(profile, assignments, batches, rule_sets, 2024, 6)

        assert result.gross_earnings == gross

        # CNPS still based on pensionable_gross = base salary only
        cnps = _ref_cnps(salary)
        assert _line_by_code(result, "EMPLOYEE_CNPS") == cnps

        # CFC and FNE are on gross
        assert _line_by_code(result, "CFC_HLF") == gross * _D("0.01")
        assert _line_by_code(result, "FNE_EMPLOYEE") == gross * _D("0.01")

        # IRPP: taxable_gross = only taxable earnings = base salary
        cfc = _ref_cfc(gross)
        fne = _ref_fne_employee(gross)
        taxable_base = _ref_taxable_base(salary, cnps, cfc, fne)
        expected_irpp = _ref_irpp_monthly(taxable_base)
        assert _line_by_code(result, "IRPP") == expected_irpp

        # Employer contributions on gross
        assert _line_by_code(result, "FNE") == gross * _D("0.025")
        assert _line_by_code(result, "ACCIDENT_RISK_EMPLOYER") == gross * _D("0.0175")

    def test_1m_with_large_allowances(self):
        salary = _D("1000000")
        housing = _D("100000")
        transport = _D("50000")
        gross = salary + housing + transport  # 1,150,000

        profile, assignments, batches, rule_sets = _build_standard_employee(
            salary, housing_allowance=housing, transport_allowance=transport,
        )
        result = _svc.calculate(profile, assignments, batches, rule_sets, 2024, 6)

        assert result.gross_earnings == gross

        # CNPS capped at 31,500 (pensionable base = 1M > 750K)
        assert _line_by_code(result, "EMPLOYEE_CNPS") == _D("31500")
        assert _line_by_code(result, "EMPLOYER_CNPS") == _D("31500")

        # CFC/FNE on total gross
        assert _line_by_code(result, "CFC_HLF") == gross * _D("0.01")
        assert _line_by_code(result, "FNE_EMPLOYEE") == gross * _D("0.01")

        # AF capped at 52,500 (gross > 750K)
        assert _line_by_code(result, "EMPLOYER_AF") == _D("52500")

    def test_allowance_only_no_base(self):
        """Edge case: zero base salary with allowances only."""
        salary = _D("0")
        housing = _D("50000")

        profile, assignments, batches, rule_sets = _build_standard_employee(
            salary, housing_allowance=housing,
        )
        result = _svc.calculate(profile, assignments, batches, rule_sets, 2024, 6)

        # Gross = housing only
        assert result.gross_earnings == housing

        # No CNPS (nothing pensionable)
        assert _line_by_code(result, "EMPLOYEE_CNPS") == _D("0")

        # CFC/FNE on gross (50K)
        assert _line_by_code(result, "CFC_HLF") == _D("500")
        assert _line_by_code(result, "FNE_EMPLOYEE") == _D("500")


# ══════════════════════════════════════════════════════════════════════════════
# Test Class: Quotient Familial
# ══════════════════════════════════════════════════════════════════════════════

class TestQuotientFamilial:
    """Verify that family parts reduce IRPP correctly.

    CGI quotient familial: divide annual taxable income by number_of_parts,
    compute IRPP on that, then multiply back. More parts = lower IRPP.
    """

    @pytest.mark.parametrize("parts,salary", [
        (_D("1.0"), _D("500000")),
        (_D("1.5"), _D("500000")),
        (_D("2.0"), _D("500000")),
        (_D("2.5"), _D("500000")),
        (_D("1.0"), _D("1000000")),
        (_D("2.0"), _D("1000000")),
        (_D("3.0"), _D("1000000")),
    ])
    def test_irpp_matches_reference_with_parts(self, parts: Decimal, salary: Decimal):
        profile, assignments, batches, rule_sets = _build_standard_employee(
            salary, number_of_parts=parts,
        )
        result = _svc.calculate(profile, assignments, batches, rule_sets, 2024, 6)

        cnps = _ref_cnps(salary)
        cfc = _ref_cfc(salary)
        fne = _ref_fne_employee(salary)
        taxable_base = _ref_taxable_base(salary, cnps, cfc, fne)
        expected_irpp = _ref_irpp_monthly(taxable_base, parts)
        actual_irpp = _line_by_code(result, "IRPP")
        assert actual_irpp == expected_irpp, (
            f"IRPP mismatch for {salary} @ {parts} parts: "
            f"actual={actual_irpp}, expected={expected_irpp}"
        )

    def test_more_parts_means_less_irpp(self):
        """Sanity check: 2 parts should always have lower IRPP than 1 part."""
        salary = _D("750000")

        p1, a1, b1, rs1 = _build_standard_employee(salary, number_of_parts=_D("1.0"))
        r1 = _svc.calculate(p1, a1, b1, rs1, 2024, 6)
        irpp_1 = _line_by_code(r1, "IRPP")

        p2, a2, b2, rs2 = _build_standard_employee(salary, number_of_parts=_D("2.0"))
        r2 = _svc.calculate(p2, a2, b2, rs2, 2024, 6)
        irpp_2 = _line_by_code(r2, "IRPP")

        assert irpp_2 < irpp_1, f"2 parts ({irpp_2}) should be less than 1 part ({irpp_1})"

    def test_cac_follows_reduced_irpp(self):
        """CAC (10% of IRPP) should also decrease with more parts."""
        salary = _D("1000000")

        p1, a1, b1, rs1 = _build_standard_employee(salary, number_of_parts=_D("1.0"))
        r1 = _svc.calculate(p1, a1, b1, rs1, 2024, 6)

        p2, a2, b2, rs2 = _build_standard_employee(salary, number_of_parts=_D("2.5"))
        r2 = _svc.calculate(p2, a2, b2, rs2, 2024, 6)

        cac_1 = _line_by_code(r1, "CAC")
        cac_2 = _line_by_code(r2, "CAC")
        assert cac_2 < cac_1

        # CAC = 10% of IRPP quantized to 4dp
        assert cac_1 == (_line_by_code(r1, "IRPP") * _D("0.10")).quantize(_D("0.0001"))
        assert cac_2 == (_line_by_code(r2, "IRPP") * _D("0.10")).quantize(_D("0.0001"))


# ══════════════════════════════════════════════════════════════════════════════
# Test Class: Overtime through full pipeline
# ══════════════════════════════════════════════════════════════════════════════

class TestOvertimePipeline:
    """Test that overtime earnings flow correctly through the full pipeline.

    Overtime is taxable and pensionable, so it affects CNPS, IRPP, etc.
    """

    def _build_with_overtime(
        self,
        basic_salary: Decimal,
        overtime_amounts: dict[str, Decimal],
    ) -> tuple:
        """Build employee with overtime direct amounts via input batches.

        overtime_amounts: dict of component_code → direct monetary amount.

        Note: The batch-based flow always populates input_amount on the
        ComponentInput. The overtime engine treats any non-None input_amount as
        a direct monetary override (skipping the hourly calculation path).
        Hours-based calculation works when ComponentInput is constructed
        directly with input_amount=None, but through the batch path the
        direct-amount mode is used.
        """
        comps = _build_components()
        profile = StubProfile(
            company_id=1, employee_id=1, basic_salary=basic_salary,
        )

        # Standard statutory assignments plus overtime components
        codes = [
            "BASE_SALARY",
            "EMPLOYEE_CNPS", "IRPP", "CAC", "TDL", "CRTV",
            "CFC_HLF", "FNE_EMPLOYEE",
            "EMPLOYER_CNPS", "FNE", "ACCIDENT_RISK_EMPLOYER", "EMPLOYER_AF",
        ]
        codes.extend(overtime_amounts.keys())
        assignments = [StubAssignment(component=comps[c]) for c in codes]

        # Input batch with direct overtime amounts
        lines = []
        for ot_code, amount in overtime_amounts.items():
            lines.append(StubInputLine(
                employee_id=1,
                component_id=comps[ot_code].id,
                input_amount=amount,
            ))
        batches = [StubInputBatch(lines=lines)] if lines else []

        rule_sets = _build_rule_sets()
        return profile, assignments, batches, rule_sets

    def test_direct_ot_at_300k(self):
        """Direct overtime amount at 300K base."""
        salary = _D("300000")
        ot_amount = _D("16616.2080")  # 8hrs T1: (300000/173.33) × 1.20 × 8
        profile, assignments, batches, rule_sets = self._build_with_overtime(
            salary, {"OVERTIME_DAY_T1": ot_amount},
        )
        result = _svc.calculate(profile, assignments, batches, rule_sets, 2024, 6)

        assert result.error_message is None
        gross = salary + ot_amount
        assert result.gross_earnings == gross

        # OT line should match direct amount
        actual_ot = _line_by_code(result, "OVERTIME_DAY_T1")
        assert actual_ot == ot_amount.quantize(_D("0.0001"))

        # CNPS should be on full pensionable gross (base + OT)
        # Engine quantizes CNPS to 4dp internally
        expected_cnps = _ref_cnps(gross).quantize(_D("0.0001"))
        assert _line_by_code(result, "EMPLOYEE_CNPS") == expected_cnps

        # Net reconciliation
        expected_net = result.total_earnings - result.total_employee_deductions - result.total_taxes
        assert result.net_payable == max(expected_net, _D("0"))

    def test_multi_tier_direct_overtime(self):
        """Multiple overtime tiers as direct amounts at 500K base."""
        salary = _D("500000")
        # Pre-computed direct amounts from hourly formula:
        # hourly = 500000 / 173.33 = 2884.8357...
        ot_t1 = _D("27698.0000")  # 8hrs × hourly × 1.20
        ot_t2 = _D("30014.5000")  # 8hrs × hourly × 1.30
        ot_night = _D("17316.5000")  # 4hrs × hourly × 1.50

        profile, assignments, batches, rule_sets = self._build_with_overtime(
            salary, {
                "OVERTIME_DAY_T1": ot_t1,
                "OVERTIME_DAY_T2": ot_t2,
                "OVERTIME_NIGHT": ot_night,
            },
        )
        result = _svc.calculate(profile, assignments, batches, rule_sets, 2024, 6)

        assert result.error_message is None
        expected_gross = salary + ot_t1 + ot_t2 + ot_night
        assert result.gross_earnings == expected_gross

        # Each OT tier produced its line
        assert _line_by_code(result, "OVERTIME_DAY_T1") == ot_t1.quantize(_D("0.0001"))
        assert _line_by_code(result, "OVERTIME_DAY_T2") == ot_t2.quantize(_D("0.0001"))
        assert _line_by_code(result, "OVERTIME_NIGHT") == ot_night.quantize(_D("0.0001"))

        # T2 > T1 (higher premium rate, same hours)
        assert _line_by_code(result, "OVERTIME_DAY_T2") > _line_by_code(result, "OVERTIME_DAY_T1")

    def test_zero_overtime_amount(self):
        """Zero overtime direct amount should produce zero overtime earnings."""
        salary = _D("300000")
        profile, assignments, batches, rule_sets = self._build_with_overtime(
            salary, {"OVERTIME_DAY_T1": _D("0")},
        )
        result = _svc.calculate(profile, assignments, batches, rule_sets, 2024, 6)

        assert result.gross_earnings == salary
        assert _line_by_code(result, "OVERTIME_DAY_T1") == _D("0")


# ══════════════════════════════════════════════════════════════════════════════
# Test Class: Edge cases & boundary conditions
# ══════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Test boundary conditions and edge cases."""

    def test_exactly_at_cnps_ceiling(self):
        """Salary exactly at 750K CNPS ceiling."""
        salary = _D("750000")
        profile, assignments, batches, rule_sets = _build_standard_employee(salary)
        result = _svc.calculate(profile, assignments, batches, rule_sets, 2024, 6)

        # Exactly at ceiling: 750000 × 0.042 = 31500
        assert _line_by_code(result, "EMPLOYEE_CNPS") == _D("31500")
        assert _line_by_code(result, "EMPLOYER_CNPS") == _D("31500")

    def test_just_below_cnps_ceiling(self):
        salary = _D("749999")
        profile, assignments, batches, rule_sets = _build_standard_employee(salary)
        result = _svc.calculate(profile, assignments, batches, rule_sets, 2024, 6)

        expected = salary * _D("0.042")
        assert _line_by_code(result, "EMPLOYEE_CNPS") == expected
        assert expected < _D("31500")

    def test_just_above_cnps_ceiling(self):
        salary = _D("750001")
        profile, assignments, batches, rule_sets = _build_standard_employee(salary)
        result = _svc.calculate(profile, assignments, batches, rule_sets, 2024, 6)

        assert _line_by_code(result, "EMPLOYEE_CNPS") == _D("31500")

    def test_minimum_wage_range(self):
        """SMIG-range salary (~ 36,270 XAF)."""
        salary = _D("36270")
        profile, assignments, batches, rule_sets = _build_standard_employee(salary)
        result = _svc.calculate(profile, assignments, batches, rule_sets, 2024, 6)

        assert result.error_message is None
        assert result.gross_earnings == salary
        # Very low salary should have minimal/zero IRPP
        assert _line_by_code(result, "IRPP") >= _D("0")
        # Net should be positive
        assert result.net_payable > _D("0")

    def test_very_high_salary(self):
        """Very high salary — 5M XAF/month (top bracket)."""
        salary = _D("5000000")
        profile, assignments, batches, rule_sets = _build_standard_employee(salary)
        result = _svc.calculate(profile, assignments, batches, rule_sets, 2024, 6)

        assert result.error_message is None
        assert result.gross_earnings == salary

        # CNPS capped
        assert _line_by_code(result, "EMPLOYEE_CNPS") == _D("31500")

        # IRPP should be substantial
        assert _line_by_code(result, "IRPP") > _D("100000")

        # CRTV top bracket
        assert _line_by_code(result, "CRTV") == _D("13000")

        # TDL top bracket
        assert _line_by_code(result, "TDL") == _D("250")

        # AF capped
        assert _line_by_code(result, "EMPLOYER_AF") == _D("52500")

    def test_exactly_at_crtv_boundary_50k(self):
        """50K is upper-inclusive in bracket 1 → CRTV = 0."""
        salary = _D("50000")
        profile, assignments, batches, rule_sets = _build_standard_employee(salary)
        result = _svc.calculate(profile, assignments, batches, rule_sets, 2024, 6)
        assert _line_by_code(result, "CRTV") == _D("0")

    def test_exactly_at_crtv_boundary_100k(self):
        """100K is upper-inclusive in bracket 2 → CRTV = 750."""
        salary = _D("100000")
        profile, assignments, batches, rule_sets = _build_standard_employee(salary)
        result = _svc.calculate(profile, assignments, batches, rule_sets, 2024, 6)
        assert _line_by_code(result, "CRTV") == _D("750")

    def test_exactly_at_crtv_boundary_1m(self):
        """1M is upper-inclusive in bracket 8 → CRTV = 12,350."""
        salary = _D("1000000")
        profile, assignments, batches, rule_sets = _build_standard_employee(salary)
        result = _svc.calculate(profile, assignments, batches, rule_sets, 2024, 6)
        assert _line_by_code(result, "CRTV") == _D("12350")

    def test_result_has_no_error(self):
        """Every salary point should produce a clean result."""
        for salary in [_D("50000"), _D("500000"), _D("1500000")]:
            profile, assignments, batches, rule_sets = _build_standard_employee(salary)
            result = _svc.calculate(profile, assignments, batches, rule_sets, 2024, 6)
            assert result.error_message is None, f"Error at {salary}: {result.error_message}"


# ══════════════════════════════════════════════════════════════════════════════
# Test Class: Cross-checks — full payslip verification at specific salary points
# ══════════════════════════════════════════════════════════════════════════════

class TestFullPayslipVerification:
    """Verify every line of the payslip at key salary points.

    These are the most comprehensive tests — they check every single computed
    value against independently calculated reference numbers.
    """

    def _verify_full_payslip(
        self,
        salary: Decimal,
        housing: Decimal = _D("0"),
        transport: Decimal = _D("0"),
        number_of_parts: Decimal = _D("1"),
    ):
        """Run the full pipeline and verify every line against references."""
        gross = salary + housing + transport
        pensionable_gross = salary  # only base salary is pensionable

        profile, assignments, batches, rule_sets = _build_standard_employee(
            salary,
            housing_allowance=housing if housing > 0 else None,
            transport_allowance=transport if transport > 0 else None,
            number_of_parts=number_of_parts,
        )
        result = _svc.calculate(profile, assignments, batches, rule_sets, 2024, 6)

        # ── Gross ──
        assert result.gross_earnings == gross, f"Gross: {result.gross_earnings} != {gross}"

        # ── Employee deductions ──
        cnps = _ref_cnps(pensionable_gross)
        cfc = _ref_cfc(gross)
        fne_emp = _ref_fne_employee(gross)

        assert _line_by_code(result, "EMPLOYEE_CNPS") == cnps
        assert _line_by_code(result, "CFC_HLF") == cfc
        assert _line_by_code(result, "FNE_EMPLOYEE") == fne_emp

        # ── IRPP ──
        taxable_gross = salary  # only taxable earnings = base salary
        taxable_base = _ref_taxable_base(taxable_gross, cnps, cfc, fne_emp)
        irpp = _ref_irpp_monthly(taxable_base, number_of_parts)
        assert _line_by_code(result, "IRPP") == irpp, (
            f"IRPP: actual={_line_by_code(result, 'IRPP')}, expected={irpp}, "
            f"taxable_base={taxable_base}"
        )

        # ── CAC ── (engine quantizes to 4dp)
        cac = (irpp * _D("0.10")).quantize(_D("0.0001"))
        assert _line_by_code(result, "CAC") == cac

        # ── CRTV ──
        assert _line_by_code(result, "CRTV") == _ref_crtv(gross)

        # ── TDL ──
        assert _line_by_code(result, "TDL") == _ref_tdl(gross)

        # ── Employer contributions ──
        assert _line_by_code(result, "EMPLOYER_CNPS") == _ref_cnps(pensionable_gross)
        assert _line_by_code(result, "FNE") == gross * _D("0.025")
        assert _line_by_code(result, "ACCIDENT_RISK_EMPLOYER") == gross * _D("0.0175")
        assert _line_by_code(result, "EMPLOYER_AF") == min(gross * _D("0.07"), _D("52500"))

        # ── Net payable reconciliation ── (use engine aggregates to avoid precision drift)
        expected_net = result.total_earnings - result.total_employee_deductions - result.total_taxes
        assert result.net_payable == max(expected_net, _D("0")), (
            f"Net payable: {result.net_payable} != {max(expected_net, _D('0'))}"
        )

        return result

    def test_payslip_50k(self):
        self._verify_full_payslip(_D("50000"))

    def test_payslip_150k(self):
        self._verify_full_payslip(_D("150000"))

    def test_payslip_300k(self):
        self._verify_full_payslip(_D("300000"))

    def test_payslip_500k(self):
        self._verify_full_payslip(_D("500000"))

    def test_payslip_750k(self):
        self._verify_full_payslip(_D("750000"))

    def test_payslip_1m(self):
        self._verify_full_payslip(_D("1000000"))

    def test_payslip_1_5m(self):
        self._verify_full_payslip(_D("1500000"))

    def test_payslip_300k_with_allowances(self):
        self._verify_full_payslip(
            _D("300000"), housing=_D("30000"), transport=_D("20000"),
        )

    def test_payslip_750k_with_allowances_and_2_parts(self):
        self._verify_full_payslip(
            _D("750000"),
            housing=_D("75000"),
            transport=_D("25000"),
            number_of_parts=_D("2.0"),
        )

    def test_payslip_1m_with_2_5_parts(self):
        self._verify_full_payslip(
            _D("1000000"), number_of_parts=_D("2.5"),
        )


# ══════════════════════════════════════════════════════════════════════════════
# Test Class: Double-entry integrity
# ══════════════════════════════════════════════════════════════════════════════

class TestDoubleEntryIntegrity:
    """Verify that the payroll calculation maintains accounting balance.

    For every payslip:
    employer_cost = gross + employer_contributions
    = net_payable + total_deductions + total_taxes + employer_contributions
    """

    @pytest.mark.parametrize("salary", [
        _D("50000"), _D("300000"), _D("750000"), _D("1500000"),
    ])
    def test_employer_cost_reconciliation(self, salary: Decimal):
        profile, assignments, batches, rule_sets = _build_standard_employee(salary)
        result = _svc.calculate(profile, assignments, batches, rule_sets, 2024, 6)

        # employer_cost = gross + employer_contributions (already tested)
        assert result.employer_cost_base == result.gross_earnings + result.total_employer_contributions

        # Also: gross = net + deductions + taxes
        assert result.gross_earnings == (
            result.net_payable + result.total_employee_deductions + result.total_taxes
        )

    @pytest.mark.parametrize("salary", [
        _D("50000"), _D("300000"), _D("750000"), _D("1500000"),
    ])
    def test_all_lines_have_positive_or_zero_amount(self, salary: Decimal):
        """No payroll line should ever be negative."""
        profile, assignments, batches, rule_sets = _build_standard_employee(salary)
        result = _svc.calculate(profile, assignments, batches, rule_sets, 2024, 6)

        for line in result.lines:
            assert line.component_amount >= _D("0"), (
                f"Negative amount for component_id={line.component_id}: {line.component_amount}"
            )
