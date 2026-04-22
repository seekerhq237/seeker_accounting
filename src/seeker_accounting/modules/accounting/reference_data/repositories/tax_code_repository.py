from __future__ import annotations

from datetime import date

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.accounting.reference_data.models.tax_code import TaxCode


class TaxCodeRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(self, company_id: int, active_only: bool = False) -> list[TaxCode]:
        statement = select(TaxCode).where(TaxCode.company_id == company_id)
        if active_only:
            statement = statement.where(TaxCode.is_active.is_(True))
        statement = statement.order_by(TaxCode.code.asc(), TaxCode.effective_from.desc(), TaxCode.id.asc())
        return list(self._session.scalars(statement))

    def get_by_id(self, company_id: int, tax_code_id: int) -> TaxCode | None:
        statement = select(TaxCode).where(
            TaxCode.company_id == company_id,
            TaxCode.id == tax_code_id,
        )
        return self._session.scalar(statement)

    def get_by_code_and_effective_from(self, company_id: int, code: str, effective_from: date) -> TaxCode | None:
        statement = select(TaxCode).where(
            TaxCode.company_id == company_id,
            TaxCode.code == code,
            TaxCode.effective_from == effective_from,
        )
        return self._session.scalar(statement)

    def add(self, tax_code: TaxCode) -> TaxCode:
        self._session.add(tax_code)
        return tax_code

    def save(self, tax_code: TaxCode) -> TaxCode:
        self._session.add(tax_code)
        return tax_code

    def code_effective_from_exists(
        self,
        company_id: int,
        code: str,
        effective_from: date,
        exclude_tax_code_id: int | None = None,
    ) -> bool:
        predicate = (
            (TaxCode.company_id == company_id)
            & (TaxCode.code == code)
            & (TaxCode.effective_from == effective_from)
        )
        if exclude_tax_code_id is not None:
            predicate = predicate & (TaxCode.id != exclude_tax_code_id)
        return bool(self._session.scalar(select(exists().where(predicate))))
