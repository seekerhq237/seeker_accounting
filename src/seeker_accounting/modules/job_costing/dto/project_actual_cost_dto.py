from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ProjectActualCostSourceTotalDTO:
    source_type_code: str
    source_type_label: str
    amount: Decimal


@dataclass(frozen=True, slots=True)
class ProjectActualCostBreakdownItemDTO:
    source_type_code: str
    source_type_label: str
    project_job_id: int | None
    project_job_code: str | None
    project_job_name: str | None
    project_cost_code_id: int | None
    project_cost_code: str | None
    project_cost_code_name: str | None
    amount: Decimal


@dataclass(frozen=True, slots=True)
class ProjectActualCostSummaryDTO:
    project_id: int
    project_code: str
    project_name: str
    contract_id: int | None
    contract_number: str | None
    currency_code: str | None
    total_actual_cost_amount: Decimal
    source_totals: tuple[ProjectActualCostSourceTotalDTO, ...]


@dataclass(frozen=True, slots=True)
class ProjectActualCostBreakdownDTO:
    summary: ProjectActualCostSummaryDTO
    items: tuple[ProjectActualCostBreakdownItemDTO, ...]