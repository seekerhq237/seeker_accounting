"""Repository for ``TaxReturn``."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.taxation.models.tax_return import TaxReturn


class TaxReturnRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, company_id: int, return_id: int) -> TaxReturn | None:
        stmt = (
            select(TaxReturn)
            .where(
                TaxReturn.id == return_id,
                TaxReturn.company_id == company_id,
            )
            .options(selectinload(TaxReturn.lines), selectinload(TaxReturn.payments))
        )
        return self._session.scalar(stmt)

    def get_by_obligation(
        self, company_id: int, obligation_id: int
    ) -> TaxReturn | None:
        stmt = select(TaxReturn).where(
            TaxReturn.company_id == company_id,
            TaxReturn.obligation_id == obligation_id,
        )
        return self._session.scalar(stmt)

    def list_by_company(
        self,
        company_id: int,
        *,
        status_code: str | None = None,
    ) -> list[TaxReturn]:
        stmt = select(TaxReturn).where(TaxReturn.company_id == company_id)
        if status_code is not None:
            stmt = stmt.where(TaxReturn.status_code == status_code)
        stmt = stmt.order_by(TaxReturn.period_end.desc(), TaxReturn.id.desc())
        return list(self._session.scalars(stmt))

    def add(self, tax_return: TaxReturn) -> TaxReturn:
        self._session.add(tax_return)
        return tax_return

    def save(self, tax_return: TaxReturn) -> TaxReturn:
        self._session.add(tax_return)
        return tax_return
