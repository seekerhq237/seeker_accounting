"""DTOs for payroll approval routing — P7.

These are plain frozen dataclasses used to cross the service boundary.
No ORM objects leak through.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ApproverConfigDTO:
    """Read projection of a :class:`PayrollApproverConfig` record."""

    id: int
    company_id: int
    approver_user_id: int
    min_run_amount: Decimal | None
    is_active: bool


@dataclass(frozen=True)
class SetApproverConfigCommand:
    """Input for adding a new approval routing rule."""

    approver_user_id: int
    min_run_amount: Decimal | None = None


@dataclass(frozen=True)
class ApprovalRoutingResultDTO:
    """Result of routing logic for a specific run total."""

    required_approver_user_id: int | None
    routing_reason: str
