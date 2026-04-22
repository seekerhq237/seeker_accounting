from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


# ── Read DTOs ────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CompanyPayrollSettingsDTO:
    company_id: int
    statutory_pack_version_code: str | None
    cnps_regime_code: str | None
    accident_risk_class_code: str | None
    default_pay_frequency_code: str
    default_payroll_currency_code: str
    overtime_policy_mode_code: str | None
    benefit_in_kind_policy_mode_code: str | None
    payroll_number_prefix: str | None
    payroll_number_padding_width: int | None
    updated_at: datetime
    updated_by_user_id: int | None


@dataclass(frozen=True, slots=True)
class DepartmentDTO:
    id: int
    company_id: int
    code: str
    name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PositionDTO:
    id: int
    company_id: int
    code: str
    name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ── Commands ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class UpsertCompanyPayrollSettingsCommand:
    default_pay_frequency_code: str
    default_payroll_currency_code: str
    statutory_pack_version_code: str | None = field(default=None)
    cnps_regime_code: str | None = field(default=None)
    accident_risk_class_code: str | None = field(default=None)
    overtime_policy_mode_code: str | None = field(default=None)
    benefit_in_kind_policy_mode_code: str | None = field(default=None)
    payroll_number_prefix: str | None = field(default=None)
    payroll_number_padding_width: int | None = field(default=None)
    updated_by_user_id: int | None = field(default=None)


@dataclass(frozen=True, slots=True)
class CreateDepartmentCommand:
    code: str
    name: str


@dataclass(frozen=True, slots=True)
class UpdateDepartmentCommand:
    code: str
    name: str
    is_active: bool


@dataclass(frozen=True, slots=True)
class CreatePositionCommand:
    code: str
    name: str


@dataclass(frozen=True, slots=True)
class UpdatePositionCommand:
    code: str
    name: str
    is_active: bool
