from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CreateProjectCostCodeCommand:
    company_id: int
    code: str
    name: str
    cost_code_type_code: str
    default_account_id: int | None = None
    description: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateProjectCostCodeCommand:
    name: str
    cost_code_type_code: str
    default_account_id: int | None = None
    description: str | None = None
