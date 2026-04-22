from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ProjectCostCodeListItemDTO:
    id: int
    code: str
    name: str
    cost_code_type_code: str
    default_account_code: str | None
    is_active: bool
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class ProjectCostCodeDetailDTO:
    id: int
    company_id: int
    code: str
    name: str
    cost_code_type_code: str
    default_account_id: int | None
    default_account_code: str | None
    is_active: bool
    description: str | None
    created_at: datetime | None
    updated_at: datetime | None
