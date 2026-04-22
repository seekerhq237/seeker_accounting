from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class BudgetControlCheckDTO:
    """Result of a budget control check against the current approved budget."""

    project_id: int
    budget_version_id: int | None
    budget_total: Decimal
    control_mode: str  # "none", "warn", "hard_stop"
    requested_amount: Decimal
    committed_amount: Decimal  # placeholder — zero until commitments exist
    actual_amount: Decimal  # placeholder — zero until actual-cost integration exists
    remaining_before_request: Decimal
    remaining_after_request: Decimal
    would_exceed_budget: bool
    message: str
