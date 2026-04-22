from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.accounting.fiscal_periods.models.fiscal_year import FiscalYear


class FiscalYearRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(self, company_id: int, active_only: bool = False) -> list[FiscalYear]:
        statement = select(FiscalYear).where(FiscalYear.company_id == company_id)
        if active_only:
            statement = statement.where(FiscalYear.is_active.is_(True))
        statement = statement.order_by(FiscalYear.start_date.asc(), FiscalYear.id.asc())
        return list(self._session.scalars(statement))

    def get_by_id(self, company_id: int, fiscal_year_id: int) -> FiscalYear | None:
        statement = select(FiscalYear).where(
            FiscalYear.company_id == company_id,
            FiscalYear.id == fiscal_year_id,
        )
        return self._session.scalar(statement)

    def get_by_code(self, company_id: int, year_code: str) -> FiscalYear | None:
        statement = select(FiscalYear).where(
            FiscalYear.company_id == company_id,
            FiscalYear.year_code == year_code,
        )
        return self._session.scalar(statement)

    def get_covering_date(self, company_id: int, target_date: date) -> FiscalYear | None:
        statement = select(FiscalYear).where(
            FiscalYear.company_id == company_id,
            FiscalYear.start_date <= target_date,
            FiscalYear.end_date >= target_date,
        )
        statement = statement.order_by(FiscalYear.start_date.desc(), FiscalYear.id.desc())
        return self._session.scalar(statement)

    def add(self, fiscal_year: FiscalYear) -> FiscalYear:
        self._session.add(fiscal_year)
        return fiscal_year

    def save(self, fiscal_year: FiscalYear) -> FiscalYear:
        self._session.add(fiscal_year)
        return fiscal_year
