from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CreateAccountCommand:
    account_code: str
    account_name: str
    account_class_id: int
    account_type_id: int
    normal_balance: str
    allow_manual_posting: bool
    is_control_account: bool
    parent_account_id: int | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateAccountCommand:
    account_code: str
    account_name: str
    account_class_id: int
    account_type_id: int
    normal_balance: str
    allow_manual_posting: bool
    is_control_account: bool
    is_active: bool
    parent_account_id: int | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class SeedBuiltInChartCommand:
    template_code: str = "ohada_syscohada_v1"
    add_missing_only: bool = True

