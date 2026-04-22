from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.accounting.fiscal_periods.models.fiscal_period import FiscalPeriod


class FiscalPeriodRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(self, company_id: int, fiscal_year_id: int | None = None) -> list[FiscalPeriod]:
        statement = select(FiscalPeriod).where(FiscalPeriod.company_id == company_id)
        if fiscal_year_id is not None:
            statement = statement.where(FiscalPeriod.fiscal_year_id == fiscal_year_id)
        statement = statement.order_by(
            FiscalPeriod.start_date.asc(),
            FiscalPeriod.period_number.asc(),
            FiscalPeriod.id.asc(),
        )
        return list(self._session.scalars(statement))

    def get_by_id(self, company_id: int, fiscal_period_id: int) -> FiscalPeriod | None:
        statement = select(FiscalPeriod).where(
            FiscalPeriod.company_id == company_id,
            FiscalPeriod.id == fiscal_period_id,
        )
        return self._session.scalar(statement)

    def get_covering_date(self, company_id: int, target_date: date) -> FiscalPeriod | None:
        statement = select(FiscalPeriod).where(
            FiscalPeriod.company_id == company_id,
            FiscalPeriod.start_date <= target_date,
            FiscalPeriod.end_date >= target_date,
        )
        statement = statement.order_by(FiscalPeriod.start_date.desc(), FiscalPeriod.id.desc())
        return self._session.scalar(statement)

    def list_for_year(self, company_id: int, fiscal_year_id: int) -> list[FiscalPeriod]:
        return self.list_by_company(company_id, fiscal_year_id=fiscal_year_id)

    def add(self, period: FiscalPeriod) -> FiscalPeriod:
        self._session.add(period)
        return period

    def save(self, period: FiscalPeriod) -> FiscalPeriod:
        self._session.add(period)
        return period
