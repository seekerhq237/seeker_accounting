"""Repository for ``TaxObligation``."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.taxation.models.tax_obligation import TaxObligation


class TaxObligationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, company_id: int, obligation_id: int) -> TaxObligation | None:
        stmt = select(TaxObligation).where(
            TaxObligation.id == obligation_id,
            TaxObligation.company_id == company_id,
        )
        return self._session.scalar(stmt)

    def get_by_period(
        self,
        company_id: int,
        tax_type_code: str,
        period_start: date,
        period_end: date,
    ) -> TaxObligation | None:
        stmt = select(TaxObligation).where(
            TaxObligation.company_id == company_id,
            TaxObligation.tax_type_code == tax_type_code,
            TaxObligation.period_start == period_start,
            TaxObligation.period_end == period_end,
        )
        return self._session.scalar(stmt)

    def list_by_company(
        self,
        company_id: int,
        *,
        tax_type_code: str | None = None,
        status_code: str | None = None,
    ) -> list[TaxObligation]:
        stmt = select(TaxObligation).where(TaxObligation.company_id == company_id)
        if tax_type_code is not None:
            stmt = stmt.where(TaxObligation.tax_type_code == tax_type_code)
        if status_code is not None:
            stmt = stmt.where(TaxObligation.status_code == status_code)
        stmt = stmt.order_by(TaxObligation.due_date.asc(), TaxObligation.id.asc())
        return list(self._session.scalars(stmt))

    def add(self, obligation: TaxObligation) -> TaxObligation:
        self._session.add(obligation)
        return obligation

    def save(self, obligation: TaxObligation) -> TaxObligation:
        self._session.add(obligation)
        return obligation
