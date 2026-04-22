from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class AccountRoleOptionDTO:
    role_code: str
    label: str
    description: str


@dataclass(frozen=True, slots=True)
class AccountRoleMappingDTO:
    role_code: str
    role_label: str
    account_id: int | None
    account_code: str | None
    account_name: str | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class SetAccountRoleMappingCommand:
    role_code: str
    account_id: int

