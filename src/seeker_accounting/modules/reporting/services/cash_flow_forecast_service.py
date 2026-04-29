"""CashFlowForecastService — read-only cash flow projection.

Projects net cash position over a horizon by combining:
- current cash balance (posted JEs against bank/cash GL accounts)
- expected receipts from open AR documents (by due_date)
- expected payments from open AP documents (by due_date)

This service is read-only. It does not commit, post, or audit.
"""
from __future__ import annotations

from calendar import monthrange
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.reporting.dto.cash_flow_forecast_dto import (
    CashFlowBucketDTO,
    CashFlowBucketUnit,
    CashFlowForecastDTO,
)
from seeker_accounting.modules.reporting.repositories.ap_aging_report_repository import (
    APAgingDocumentRow,
    APAgingReportRepository,
)
from seeker_accounting.modules.reporting.repositories.ar_aging_report_repository import (
    ARAgingDocumentRow,
    ARAgingReportRepository,
)
from seeker_accounting.modules.reporting.repositories.cash_flow_forecast_repository import (
    CashFlowForecastRepository,
)
from seeker_accounting.modules.treasury.repositories.financial_account_repository import (
    FinancialAccountRepository,
)
from seeker_accounting.platform.exceptions import ValidationError

ARAgingReportRepositoryFactory = Callable[[Session], ARAgingReportRepository]
APAgingReportRepositoryFactory = Callable[[Session], APAgingReportRepository]
CashFlowForecastRepositoryFactory = Callable[[Session], CashFlowForecastRepository]
FinancialAccountRepositoryFactory = Callable[[Session], FinancialAccountRepository]

_ZERO = Decimal("0.00")
_MIN_BUCKETS = 1
_MAX_BUCKETS = 26


@dataclass
class _BucketAccumulator:
    label: str
    bucket_start: date | None
    bucket_end: date | None
    is_past_due: bool
    receipts: Decimal = Decimal("0.00")
    payments: Decimal = Decimal("0.00")
    receipts_count: int = 0
    payments_count: int = 0


class CashFlowForecastService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        ar_aging_report_repository_factory: ARAgingReportRepositoryFactory,
        ap_aging_report_repository_factory: APAgingReportRepositoryFactory,
        cash_flow_forecast_repository_factory: CashFlowForecastRepositoryFactory,
        financial_account_repository_factory: FinancialAccountRepositoryFactory,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._ar_repo_factory = ar_aging_report_repository_factory
        self._ap_repo_factory = ap_aging_report_repository_factory
        self._cash_repo_factory = cash_flow_forecast_repository_factory
        self._fa_repo_factory = financial_account_repository_factory

    def forecast(
        self,
        company_id: int,
        as_of_date: date,
        *,
        bucket_unit: CashFlowBucketUnit = CashFlowBucketUnit.WEEK,
        bucket_count: int = 8,
        include_ar: bool = True,
        include_ap: bool = True,
    ) -> CashFlowForecastDTO:
        if as_of_date is None:
            raise ValidationError("As-of date is required.")
        if not (_MIN_BUCKETS <= bucket_count <= _MAX_BUCKETS):
            raise ValidationError(
                f"Bucket count must be between {_MIN_BUCKETS} and {_MAX_BUCKETS}."
            )
        if not (include_ar or include_ap):
            raise ValidationError(
                "Select at least one of expected receipts (AR) or "
                "expected payments (AP)."
            )

        warnings: list[str] = []

        with self._uow_factory() as uow:
            fa_repo = self._fa_repo_factory(uow.session)
            cash_repo = self._cash_repo_factory(uow.session)

            financial_accounts = fa_repo.list_by_company(company_id, active_only=True)
            gl_account_ids = [fa.gl_account_id for fa in financial_accounts]
            opening_balance = cash_repo.sum_cash_balance_as_of(
                company_id, gl_account_ids, as_of_date
            )
            cash_account_count = len(gl_account_ids)
            if cash_account_count == 0:
                warnings.append(
                    "No active bank/cash accounts are configured. Opening "
                    "cash balance is shown as zero."
                )

            ar_rows: list[ARAgingDocumentRow] = []
            ap_rows: list[APAgingDocumentRow] = []
            if include_ar:
                ar_rows = self._ar_repo_factory(uow.session).list_open_documents(
                    company_id, as_of_date
                )
            if include_ap:
                ap_rows = self._ap_repo_factory(uow.session).list_open_documents(
                    company_id, as_of_date
                )

        accumulators = _build_buckets(as_of_date, bucket_unit, bucket_count)
        out_of_range_receipts = _ZERO
        out_of_range_payments = _ZERO
        undated_receipts = _ZERO
        undated_payments = _ZERO
        undated_ar_count = 0
        undated_ap_count = 0

        for ar in ar_rows:
            amount = _abs(ar.open_amount)
            if ar.due_date is None:
                undated_receipts += amount
                undated_ar_count += 1
                continue
            idx = _bucket_index(ar.due_date, as_of_date, accumulators)
            if idx is None:
                out_of_range_receipts += amount
                continue
            accumulators[idx].receipts += amount
            accumulators[idx].receipts_count += 1

        for ap in ap_rows:
            amount = _abs(ap.open_amount)
            if ap.due_date is None:
                undated_payments += amount
                undated_ap_count += 1
                continue
            idx = _bucket_index(ap.due_date, as_of_date, accumulators)
            if idx is None:
                out_of_range_payments += amount
                continue
            accumulators[idx].payments += amount
            accumulators[idx].payments_count += 1

        if undated_ar_count > 0:
            warnings.append(
                f"{undated_ar_count} open AR document(s) have no due date and "
                "are not placed into any bucket."
            )
        if undated_ap_count > 0:
            warnings.append(
                f"{undated_ap_count} open AP document(s) have no due date and "
                "are not placed into any bucket."
            )

        running = opening_balance.quantize(Decimal("0.01"))
        bucket_dtos: list[CashFlowBucketDTO] = []
        for idx, acc in enumerate(accumulators):
            opening = running
            net = (acc.receipts - acc.payments).quantize(Decimal("0.01"))
            closing = (opening + net).quantize(Decimal("0.01"))
            running = closing
            bucket_dtos.append(
                CashFlowBucketDTO(
                    index=idx,
                    label=acc.label,
                    bucket_start=acc.bucket_start,
                    bucket_end=acc.bucket_end,
                    is_past_due=acc.is_past_due,
                    expected_receipts=acc.receipts.quantize(Decimal("0.01")),
                    expected_payments=acc.payments.quantize(Decimal("0.01")),
                    receipts_document_count=acc.receipts_count,
                    payments_document_count=acc.payments_count,
                    opening_balance=opening,
                    closing_balance=closing,
                )
            )

        if any(b.closing_balance < _ZERO for b in bucket_dtos):
            warnings.append(
                "Projected cash position goes negative in at least one bucket. "
                "Review payment timing or accelerate collections."
            )

        return CashFlowForecastDTO(
            company_id=company_id,
            as_of_date=as_of_date,
            bucket_unit=bucket_unit,
            bucket_count=bucket_count,
            include_ar=include_ar,
            include_ap=include_ap,
            opening_cash_balance=opening_balance.quantize(Decimal("0.01")),
            cash_account_count=cash_account_count,
            buckets=tuple(bucket_dtos),
            out_of_range_receipts=out_of_range_receipts.quantize(Decimal("0.01")),
            out_of_range_payments=out_of_range_payments.quantize(Decimal("0.01")),
            undated_receipts=undated_receipts.quantize(Decimal("0.01")),
            undated_payments=undated_payments.quantize(Decimal("0.01")),
            warnings=tuple(warnings),
        )


# ---------------------------------------------------------------------- #
# Helpers                                                                  #
# ---------------------------------------------------------------------- #


def _abs(value: Decimal) -> Decimal:
    return value if value >= 0 else -value


def _build_buckets(
    as_of_date: date,
    unit: CashFlowBucketUnit,
    count: int,
) -> list[_BucketAccumulator]:
    """Build past-due + N forward buckets starting the day after as_of_date."""
    buckets: list[_BucketAccumulator] = [
        _BucketAccumulator(
            label="Past due",
            bucket_start=None,
            bucket_end=as_of_date,
            is_past_due=True,
        )
    ]
    cursor = as_of_date + timedelta(days=1)
    for i in range(count):
        if unit is CashFlowBucketUnit.WEEK:
            start = cursor
            end = start + timedelta(days=6)
            label = f"Week {i + 1} ({start.isoformat()} → {end.isoformat()})"
            buckets.append(
                _BucketAccumulator(
                    label=label,
                    bucket_start=start,
                    bucket_end=end,
                    is_past_due=False,
                )
            )
            cursor = end + timedelta(days=1)
        else:
            start = cursor
            last_day = monthrange(start.year, start.month)[1]
            end = date(start.year, start.month, last_day)
            label = f"{start.strftime('%b %Y')}"
            buckets.append(
                _BucketAccumulator(
                    label=label,
                    bucket_start=start,
                    bucket_end=end,
                    is_past_due=False,
                )
            )
            cursor = end + timedelta(days=1)
    return buckets


def _bucket_index(
    due_date: date,
    as_of_date: date,
    buckets: list[_BucketAccumulator],
) -> int | None:
    """Return the bucket index for a due date, or None if past horizon."""
    if due_date <= as_of_date:
        return 0
    for i, bucket in enumerate(buckets):
        if bucket.is_past_due:
            continue
        if bucket.bucket_start is None or bucket.bucket_end is None:
            continue
        if bucket.bucket_start <= due_date <= bucket.bucket_end:
            return i
    return None
