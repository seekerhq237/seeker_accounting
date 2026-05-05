"""Repository for VatPeriodLock (T43)."""
from __future__ import annotations

import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.taxation.models.vat_period_lock import VatPeriodLock


class VatPeriodLockRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def is_locked(
        self,
        company_id: int,
        tax_point_date: datetime.date,
        tax_type_code: str = "VAT",
    ) -> bool:
        """Return True if a lock exists whose period contains ``tax_point_date``."""
        stmt = select(VatPeriodLock.id).where(
            VatPeriodLock.company_id == company_id,
            VatPeriodLock.tax_type_code == tax_type_code,
            VatPeriodLock.period_start <= tax_point_date,
            VatPeriodLock.period_end >= tax_point_date,
        ).limit(1)
        return self._session.scalar(stmt) is not None

    def find_by_period(
        self,
        company_id: int,
        period_start: datetime.date,
        period_end: datetime.date,
        tax_type_code: str = "VAT",
    ) -> VatPeriodLock | None:
        stmt = select(VatPeriodLock).where(
            VatPeriodLock.company_id == company_id,
            VatPeriodLock.period_start == period_start,
            VatPeriodLock.period_end == period_end,
            VatPeriodLock.tax_type_code == tax_type_code,
        )
        return self._session.scalar(stmt)

    def list_by_company(
        self,
        company_id: int,
        tax_type_code: str | None = None,
    ) -> list[VatPeriodLock]:
        stmt = select(VatPeriodLock).where(
            VatPeriodLock.company_id == company_id,
        )
        if tax_type_code is not None:
            stmt = stmt.where(VatPeriodLock.tax_type_code == tax_type_code)
        stmt = stmt.order_by(VatPeriodLock.period_start.desc())
        return list(self._session.scalars(stmt))

    def add(self, lock: VatPeriodLock) -> VatPeriodLock:
        self._session.add(lock)
        return lock

    def delete(self, lock: VatPeriodLock) -> None:
        self._session.delete(lock)
