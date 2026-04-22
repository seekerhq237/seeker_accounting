"""Shared input/output types for payroll calculation engines.

Engines are pure calculation units. They receive pre-loaded data and return
result lines. They do not touch the database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(slots=True)
class ComponentInput:
    """A payroll component to be processed, with its resolved effective values."""
    component_id: int
    component_code: str
    component_name: str
    component_type_code: str         # earning, deduction, employer_contribution, tax, informational
    calculation_method_code: str     # fixed_amount, percentage, rule_based, manual_input, hourly
    is_taxable: bool
    is_pensionable: bool
    base_amount: Decimal             # resolved fixed amount (from profile, assignment override, or default)
    base_rate: Decimal               # resolved rate (percentage as decimal, e.g. 0.042 for 4.2%)
    rule_code: str | None            # linked rule set code for rule_based components
    input_amount: Decimal | None     # variable input amount (from approved input batch), if any
    input_quantity: Decimal | None   # variable input quantity (e.g. overtime hours), if any


@dataclass(slots=True)
class RuleBracketInput:
    """One bracket line from a rule set, for use in engine calculations."""
    lower_bound: Decimal
    upper_bound: Decimal | None
    rate: Decimal                    # percentage as decimal (e.g. 0.10 for 10%)
    fixed_amount: Decimal
    deduction_amount: Decimal
    cap_amount: Decimal | None


@dataclass(slots=True)
class RuleSetInput:
    """A loaded effective rule set with its brackets."""
    rule_set_id: int
    rule_code: str
    rule_type_code: str
    calculation_basis_code: str
    brackets: list[RuleBracketInput] = field(default_factory=list)


@dataclass(slots=True)
class EngineLineResult:
    """One computed payroll line from an engine."""
    component_id: int
    component_type_code: str
    calculation_basis: Decimal
    rate_applied: Decimal | None
    component_amount: Decimal


@dataclass(slots=True)
class EngineContext:
    """All resolved inputs needed to run the calculation engines for one employee."""
    company_id: int
    employee_id: int
    period_year: int
    period_month: int
    basic_salary: Decimal
    currency_code: str
    components: list[ComponentInput] = field(default_factory=list)
    rule_sets: dict[str, RuleSetInput] = field(default_factory=dict)
    # rule_sets keyed by rule_code
    number_of_parts: Decimal = Decimal("1")  # Quotient familial (IRPP family parts)


@dataclass(slots=True)
class EmployeeCalculationResult:
    """Full calculation result for one employee in a payroll run."""
    employee_id: int
    lines: list[EngineLineResult] = field(default_factory=list)
    error_message: str | None = None

    # Derived after all engines run
    gross_earnings: Decimal = Decimal("0")
    taxable_salary_base: Decimal = Decimal("0")
    tdl_base: Decimal = Decimal("0")
    cnps_contributory_base: Decimal = Decimal("0")
    employer_cost_base: Decimal = Decimal("0")
    net_payable: Decimal = Decimal("0")
    total_earnings: Decimal = Decimal("0")
    total_employee_deductions: Decimal = Decimal("0")
    total_employer_contributions: Decimal = Decimal("0")
    total_taxes: Decimal = Decimal("0")
