from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class AccountLookupDTO:
    id: int
    account_code: str
    account_name: str
    is_active: bool
    is_control_account: bool = False
    allow_manual_posting: bool = True


@dataclass(frozen=True, slots=True)
class AccountListItemDTO:
    id: int
    company_id: int
    account_code: str
    account_name: str
    account_class_id: int
    account_class_code: str
    account_class_name: str
    account_type_id: int
    account_type_code: str
    account_type_name: str
    parent_account_id: int | None
    parent_account_code: str | None
    parent_account_name: str | None
    normal_balance: str
    allow_manual_posting: bool
    is_control_account: bool
    is_active: bool
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AccountDetailDTO:
    id: int
    company_id: int
    account_code: str
    account_name: str
    account_class_id: int
    account_class_code: str
    account_class_name: str
    account_type_id: int
    account_type_code: str
    account_type_name: str
    parent_account_id: int | None
    parent_account_code: str | None
    parent_account_name: str | None
    normal_balance: str
    allow_manual_posting: bool
    is_control_account: bool
    is_active: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AccountTreeNodeDTO:
    id: int
    company_id: int
    account_code: str
    account_name: str
    account_class_code: str
    account_class_name: str
    account_type_code: str
    account_type_name: str
    parent_account_id: int | None
    normal_balance: str
    allow_manual_posting: bool
    is_control_account: bool
    is_active: bool
    children: tuple["AccountTreeNodeDTO", ...] = field(default_factory=tuple)

