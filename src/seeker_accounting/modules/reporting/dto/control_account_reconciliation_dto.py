"""DTOs for the Control Account Reconciliation read-only service."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ControlAccountReconciliationDTO:
    """Snapshot of a single control account vs its subledger as at a date.

    `gl_balance` and `delta` are signed (debit-positive). `subledger_total`
    is the absolute open-balance from the aging report (always non-negative).
    `is_reconciled` is True only when the account is mapped *and* the absolute
    delta is below the materiality threshold.
    """

    role_code: str
    role_label: str
    as_of_date: date
    account_mapped: bool
    account_id: int | None = None
    account_code: str | None = None
    account_name: str | None = None
    gl_balance: Decimal | None = None
    subledger_total: Decimal = Decimal("0.00")
    party_count: int = 0
    document_count: int = 0
    delta: Decimal | None = None
    is_reconciled: bool = False


@dataclass(frozen=True, slots=True)
class ControlAccountReconciliationReportDTO:
    """Combined snapshot for a reconciliation review session."""

    company_id: int
    as_of_date: date
    sections: tuple[ControlAccountReconciliationDTO, ...] = field(default_factory=tuple)
