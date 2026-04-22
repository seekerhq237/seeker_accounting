from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ContractProjectRollupItemDTO:
    """Financial summary for a single project rolled up under a contract."""

    project_id: int
    project_code: str
    project_name: str
    currency_code: str | None
    billed_revenue_amount: Decimal
    actual_cost_amount: Decimal
    approved_commitment_amount: Decimal
    current_budget_amount: Decimal
    total_exposure_amount: Decimal
    remaining_budget_after_commitments_amount: Decimal
    margin_amount: Decimal
    margin_percent: Decimal | None


@dataclass(frozen=True, slots=True)
class ContractSummaryDTO:
    """Read-only contract financial summary derived from approved/posted facts.

    current_contract_amount = base_contract_amount + approved_change_order_delta_total
    This is derived, not stored.
    """

    company_id: int
    contract_id: int
    contract_number: str
    contract_title: str
    currency_code: str
    status_code: str
    contract_type_code: str
    base_contract_amount: Decimal
    approved_change_order_delta_total: Decimal
    current_contract_amount: Decimal
    project_rollup_items: tuple[ContractProjectRollupItemDTO, ...]
    # Cross-project totals
    total_billed_revenue_amount: Decimal
    total_actual_cost_amount: Decimal
    total_approved_commitment_amount: Decimal
    total_current_budget_amount: Decimal
    total_exposure_amount: Decimal
    total_margin_amount: Decimal
    total_margin_percent: Decimal | None
