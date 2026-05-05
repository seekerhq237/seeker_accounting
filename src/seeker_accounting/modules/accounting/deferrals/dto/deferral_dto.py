"""Deferral DTOs — commands and read models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


# ── Commands ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CreateDeferralScheduleCommand:
    """Request to create a new deferral schedule and generate its lines."""

    company_id: int
    deferral_type: str           # EXPENSE | REVENUE
    description: str
    total_amount: Decimal
    recognition_account_id: int  # The P&L account (expense or revenue)
    holding_account_id: int      # 476 (prepaid) or 477 (unearned revenue)
    start_date: date
    period_count: int            # Number of monthly recognition periods
    reference_text: str | None = None
    source_document_type: str | None = None
    source_document_id: int | None = None
    notes: str | None = None
    created_by_user_id: int | None = None


@dataclass(frozen=True)
class ActivateDeferralScheduleCommand:
    company_id: int
    schedule_id: int


@dataclass(frozen=True)
class PostRecognitionLineCommand:
    """Request to post a single recognition instalment."""

    company_id: int
    schedule_id: int
    line_id: int
    fiscal_period_id: int
    posted_by_user_id: int | None = None


@dataclass(frozen=True)
class PostAllDueCommand:
    """Post all PENDING lines due on or before as_of_date for the company."""

    company_id: int
    fiscal_period_id: int
    as_of_date: date
    posted_by_user_id: int | None = None


@dataclass(frozen=True)
class CancelDeferralScheduleCommand:
    company_id: int
    schedule_id: int
    reason: str | None = None


# ── Read models ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class DeferralLineDTO:
    id: int
    line_number: int
    recognition_date: date
    amount: Decimal
    status_code: str
    journal_entry_id: int | None


@dataclass(frozen=True)
class DeferralScheduleDTO:
    id: int
    company_id: int
    deferral_type: str
    description: str
    reference_text: str | None
    recognition_account_id: int
    holding_account_id: int
    total_amount: Decimal
    start_date: date
    end_date: date
    period_count: int
    status_code: str
    source_document_type: str | None
    source_document_id: int | None
    notes: str | None
    lines: list[DeferralLineDTO] = field(default_factory=list)

    @property
    def posted_amount(self) -> Decimal:
        return sum(
            (ln.amount for ln in self.lines if ln.status_code == "POSTED"),
            Decimal("0"),
        )

    @property
    def remaining_amount(self) -> Decimal:
        return self.total_amount - self.posted_amount
