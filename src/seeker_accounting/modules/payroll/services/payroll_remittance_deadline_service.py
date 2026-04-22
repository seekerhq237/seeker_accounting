"""Payroll Remittance Deadline Service — computes statutory filing deadlines.

Cameroon statutory remittance deadlines:
- DGI: 15th of the month following the pay period
- CNPS: 15th of the month following the pay period
- Other: no standard deadline

This service reads from existing remittance batch data and company settings.
No new truth tables.  No calendar/scheduling infrastructure.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.payroll.dto.payroll_remittance_dto import (
    PayrollRemittanceBatchListItemDTO,
)
from seeker_accounting.modules.payroll.repositories.payroll_remittance_repository import (
    PayrollRemittanceBatchRepository,
)

PayrollRemittanceBatchRepositoryFactory = Callable[[Session], PayrollRemittanceBatchRepository]


@dataclass(frozen=True, slots=True)
class RemittanceDeadlineDTO:
    """Remittance batch with computed deadline visibility."""
    batch_id: int
    batch_number: str
    authority_code: str
    authority_label: str
    period_start: date
    period_end: date
    amount_due: Decimal
    amount_paid: Decimal
    outstanding: Decimal
    status_code: str
    filing_deadline: date | None
    days_until_deadline: int | None
    is_overdue: bool


_AUTHORITY_LABELS = {
    "dgi": "DGI (Direction Générale des Impôts)",
    "cnps": "CNPS (Caisse Nationale de Prévoyance Sociale)",
    "other": "Other",
}


def compute_filing_deadline(authority_code: str, period_end_date: date) -> date | None:
    """Derive the statutory filing deadline from authority and period end date.

    DGI: 15th of the month following the period end.
    CNPS: 15th of the month following the period end.
    Other: no defined deadline.
    """
    if authority_code in ("dgi", "cnps"):
        # 15th of the month after the period end
        if period_end_date.month == 12:
            return date(period_end_date.year + 1, 1, 15)
        return date(period_end_date.year, period_end_date.month + 1, 15)

    return None


class PayrollRemittanceDeadlineService:
    """Reads existing remittance batches and annotates them with deadline visibility."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        batch_repo_factory: PayrollRemittanceBatchRepositoryFactory,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._batch_repo_factory = batch_repo_factory

    def get_outstanding_deadlines(
        self,
        company_id: int,
        *,
        as_of: date | None = None,
    ) -> list[RemittanceDeadlineDTO]:
        """Return non-cancelled/non-paid remittance batches with deadline annotations.

        Sorted by deadline (soonest first), then by authority.
        """
        reference = as_of or date.today()

        with self._uow_factory() as uow:
            repo = self._batch_repo_factory(uow.session)
            batches = repo.list_by_company(company_id)

        results: list[RemittanceDeadlineDTO] = []
        for b in batches:
            if b.status_code in ("cancelled", "paid"):
                continue

            deadline = compute_filing_deadline(b.remittance_authority_code, b.period_end_date)
            days_until = (deadline - reference).days if deadline else None
            is_overdue = days_until is not None and days_until < 0

            results.append(RemittanceDeadlineDTO(
                batch_id=b.id,
                batch_number=b.batch_number,
                authority_code=b.remittance_authority_code,
                authority_label=_AUTHORITY_LABELS.get(
                    b.remittance_authority_code, b.remittance_authority_code
                ),
                period_start=b.period_start_date,
                period_end=b.period_end_date,
                amount_due=b.amount_due,
                amount_paid=b.amount_paid,
                outstanding=b.outstanding,
                status_code=b.status_code,
                filing_deadline=deadline,
                days_until_deadline=days_until,
                is_overdue=is_overdue,
            ))

        results.sort(key=lambda d: (d.filing_deadline or date.max, d.authority_code))
        return results
