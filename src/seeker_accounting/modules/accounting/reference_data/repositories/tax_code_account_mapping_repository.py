from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.accounting.reference_data.models.tax_code_account_mapping import TaxCodeAccountMapping


class TaxCodeAccountMappingRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(self, company_id: int) -> list[TaxCodeAccountMapping]:
        statement = select(TaxCodeAccountMapping).where(TaxCodeAccountMapping.company_id == company_id)
        statement = statement.order_by(TaxCodeAccountMapping.tax_code_id.asc(), TaxCodeAccountMapping.id.asc())
        return list(self._session.scalars(statement))

    def get_by_tax_code(self, company_id: int, tax_code_id: int) -> TaxCodeAccountMapping | None:
        statement = select(TaxCodeAccountMapping).where(
            TaxCodeAccountMapping.company_id == company_id,
            TaxCodeAccountMapping.tax_code_id == tax_code_id,
        )
        return self._session.scalar(statement)

    def add(self, mapping: TaxCodeAccountMapping) -> TaxCodeAccountMapping:
        self._session.add(mapping)
        return mapping

    def save(self, mapping: TaxCodeAccountMapping) -> TaxCodeAccountMapping:
        self._session.add(mapping)
        return mapping

    def delete(self, mapping: TaxCodeAccountMapping) -> None:
        self._session.delete(mapping)

