from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ProjectProfitabilityBreakdownItemDTO:
    project_job_id: int | None
    project_job_code: str | None
    project_job_name: str | None
    project_cost_code_id: int | None
    project_cost_code: str | None
    project_cost_code_name: str | None
    billed_revenue_amount: Decimal
    actual_cost_amount: Decimal
    current_budget_amount: Decimal
    approved_open_commitment_amount: Decimal
    gross_profit_amount: Decimal
    budget_variance_amount: Decimal
    remaining_budget_after_commitments_amount: Decimal


@dataclass(frozen=True, slots=True)
class ProjectProfitabilitySummaryDTO:
    project_id: int
    project_code: str
    project_name: str
    contract_id: int | None
    contract_number: str | None
    currency_code: str | None
    billed_revenue_amount: Decimal
    actual_cost_amount: Decimal
    approved_open_commitment_amount: Decimal
    current_budget_amount: Decimal
    gross_profit_amount: Decimal
    gross_margin_percent: Decimal | None
    budget_variance_amount: Decimal
    remaining_budget_amount: Decimal
    projected_margin_after_commitments_amount: Decimal
    remaining_budget_after_commitments_amount: Decimal


@dataclass(frozen=True, slots=True)
class ProjectProfitabilityDTO:
    summary: ProjectProfitabilitySummaryDTO
    items: tuple[ProjectProfitabilityBreakdownItemDTO, ...]