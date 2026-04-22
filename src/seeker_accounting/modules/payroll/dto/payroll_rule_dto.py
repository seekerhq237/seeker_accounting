from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal


# ── Read DTOs ────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class PayrollRuleBracketDTO:
    id: int
    payroll_rule_set_id: int
    line_number: int
    lower_bound_amount: Decimal | None
    upper_bound_amount: Decimal | None
    rate_percent: Decimal | None
    fixed_amount: Decimal | None
    deduction_amount: Decimal | None
    cap_amount: Decimal | None


@dataclass(frozen=True, slots=True)
class PayrollRuleSetListItemDTO:
    id: int
    company_id: int
    rule_code: str
    rule_name: str
    rule_type_code: str
    effective_from: date
    effective_to: date | None
    calculation_basis_code: str
    is_active: bool
    bracket_count: int


@dataclass(frozen=True, slots=True)
class PayrollRuleSetDetailDTO:
    id: int
    company_id: int
    rule_code: str
    rule_name: str
    rule_type_code: str
    effective_from: date
    effective_to: date | None
    calculation_basis_code: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    brackets: tuple[PayrollRuleBracketDTO, ...]


# ── Commands ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CreatePayrollRuleSetCommand:
    rule_code: str
    rule_name: str
    rule_type_code: str
    effective_from: date
    calculation_basis_code: str
    effective_to: date | None = field(default=None)


@dataclass(frozen=True, slots=True)
class UpdatePayrollRuleSetCommand:
    rule_code: str
    rule_name: str
    rule_type_code: str
    effective_from: date
    calculation_basis_code: str
    is_active: bool
    effective_to: date | None = field(default=None)


@dataclass(frozen=True, slots=True)
class UpsertPayrollRuleBracketCommand:
    """Create or replace a single bracket line by line_number.

    All monetary/rate fields are optional to support partial bracket configs
    (e.g., flat-rate band with no deduction_amount, or cap-only band).
    """
    line_number: int
    lower_bound_amount: Decimal | None = field(default=None)
    upper_bound_amount: Decimal | None = field(default=None)
    rate_percent: Decimal | None = field(default=None)
    fixed_amount: Decimal | None = field(default=None)
    deduction_amount: Decimal | None = field(default=None)
    cap_amount: Decimal | None = field(default=None)


@dataclass(frozen=True, slots=True)
class DeletePayrollRuleBracketCommand:
    line_number: int
