from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ProjectVarianceBreakdownItemDTO:
    """Variance figures for a single dimension (job + cost-code combination).

    Used for both variance-by-cost-code and variance-by-job views.  The
    collapsed dimension will have its fields set to None and its id to None
    when the caller aggregates across it.

    variance_amount = approved_budget_amount - actual_cost_amount
    Positive means under-budget; negative means over-budget.
    """

    project_job_id: int | None
    project_job_code: str | None
    project_job_name: str | None
    project_cost_code_id: int | None
    project_cost_code: str | None
    project_cost_code_name: str | None
    approved_budget_amount: Decimal
    actual_cost_amount: Decimal
    approved_commitment_amount: Decimal
    total_exposure_amount: Decimal
    remaining_budget_amount: Decimal
    variance_amount: Decimal
    variance_percent: Decimal | None


@dataclass(frozen=True, slots=True)
class ProjectVarianceSummaryDTO:
    """Project-level variance summary with all key management-control figures."""

    project_id: int
    project_code: str
    project_name: str
    contract_id: int | None
    contract_number: str | None
    currency_code: str | None
    approved_budget_amount: Decimal
    actual_cost_amount: Decimal
    approved_commitment_amount: Decimal
    total_exposure_amount: Decimal
    remaining_budget_amount: Decimal
    remaining_budget_after_commitments_amount: Decimal
    variance_amount: Decimal
    variance_percent: Decimal | None
    billed_revenue_amount: Decimal
    margin_amount: Decimal
    margin_percent: Decimal | None


@dataclass(frozen=True, slots=True)
class ProjectControlSummaryDTO:
    """Comprehensive project control summary combining budget, actuals, commitments,
    and revenue in a single read model suitable for a project control dashboard row.
    """

    project_id: int
    project_code: str
    project_name: str
    contract_id: int | None
    contract_number: str | None
    currency_code: str | None
    current_budget_amount: Decimal
    actual_cost_amount: Decimal
    approved_open_commitment_amount: Decimal
    total_exposure_amount: Decimal
    remaining_budget_amount: Decimal
    remaining_budget_after_commitments_amount: Decimal
    variance_amount: Decimal
    variance_percent: Decimal | None
    billed_revenue_amount: Decimal
    gross_margin_amount: Decimal
    gross_margin_percent: Decimal | None


@dataclass(frozen=True, slots=True)
class ProjectTrendSeriesPointDTO:
    """A single period data point for a project cost/revenue trend chart.

    period_label is ISO year-month (e.g. "2024-03") for display use.
    Cumulative amounts accumulate from the earliest period in the series.
    """

    period_label: str
    period_year: int
    period_month: int
    actual_cost_amount: Decimal
    cumulative_actual_cost_amount: Decimal
    billed_revenue_amount: Decimal
    cumulative_billed_revenue_amount: Decimal


@dataclass(frozen=True, slots=True)
class ProjectTrendSeriesDTO:
    """Chart-ready time series for a project.

    current_budget_amount is the approved budget reference line value —
    it does not aggregate by period since budget lines carry no transaction date.
    """

    project_id: int
    project_code: str
    project_name: str
    currency_code: str | None
    current_budget_amount: Decimal
    points: tuple[ProjectTrendSeriesPointDTO, ...]
