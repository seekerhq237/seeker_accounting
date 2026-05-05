"""Repository for CompanyProRataHistory."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.taxation.models.company_pro_rata_history import (
    CompanyProRataHistory,
)


class CompanyProRataHistoryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_company_year(
        self, company_id: int, fiscal_year: int
    ) -> CompanyProRataHistory | None:
        stmt = select(CompanyProRataHistory).where(
            CompanyProRataHistory.company_id == company_id,
            CompanyProRataHistory.fiscal_year == fiscal_year,
        )
        return self._session.scalar(stmt)

    def list_by_company(
        self, company_id: int
    ) -> list[CompanyProRataHistory]:
        stmt = (
            select(CompanyProRataHistory)
            .where(CompanyProRataHistory.company_id == company_id)
            .order_by(CompanyProRataHistory.fiscal_year.desc())
        )
        return list(self._session.scalars(stmt))

    def add(self, record: CompanyProRataHistory) -> CompanyProRataHistory:
        self._session.add(record)
        return record

    def save(self, record: CompanyProRataHistory) -> None:
        self._session.add(record)
