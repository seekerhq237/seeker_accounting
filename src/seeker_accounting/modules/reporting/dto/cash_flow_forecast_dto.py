"""DTOs for the Cash Flow Forecast read-only diagnostic."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum


class CashFlowBucketUnit(str, Enum):
    WEEK = "WEEK"
    MONTH = "MONTH"


@dataclass(frozen=True)
class CashFlowBucketDTO:
    """One time bucket of the forecast (or the past-due bucket)."""

    index: int
    label: str
    bucket_start: date | None  # None for the past-due bucket
    bucket_end: date | None    # None for the past-due bucket
    is_past_due: bool
    expected_receipts: Decimal
    expected_payments: Decimal
    receipts_document_count: int
    payments_document_count: int
    opening_balance: Decimal
    closing_balance: Decimal

    @property
    def net_movement(self) -> Decimal:
        return self.expected_receipts - self.expected_payments


@dataclass(frozen=True)
class CashFlowForecastDTO:
    """Read-only forecast snapshot."""

    company_id: int
    as_of_date: date
    bucket_unit: CashFlowBucketUnit
    bucket_count: int
    include_ar: bool
    include_ap: bool
    opening_cash_balance: Decimal
    cash_account_count: int
    buckets: tuple[CashFlowBucketDTO, ...] = field(default_factory=tuple)
    out_of_range_receipts: Decimal = Decimal("0.00")
    out_of_range_payments: Decimal = Decimal("0.00")
    undated_receipts: Decimal = Decimal("0.00")
    undated_payments: Decimal = Decimal("0.00")
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def total_expected_receipts(self) -> Decimal:
        return sum((b.expected_receipts for b in self.buckets), Decimal("0.00"))

    @property
    def total_expected_payments(self) -> Decimal:
        return sum((b.expected_payments for b in self.buckets), Decimal("0.00"))

    @property
    def closing_cash_balance(self) -> Decimal:
        if not self.buckets:
            return self.opening_cash_balance
        return self.buckets[-1].closing_balance

    @property
    def has_negative_bucket(self) -> bool:
        return any(b.closing_balance < Decimal("0") for b in self.buckets)
