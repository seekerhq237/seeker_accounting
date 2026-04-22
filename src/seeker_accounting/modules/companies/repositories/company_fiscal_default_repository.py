from __future__ import annotations

from sqlalchemy.orm import Session

from seeker_accounting.modules.companies.models.company_fiscal_default import CompanyFiscalDefault


class CompanyFiscalDefaultRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_company_id(self, company_id: int) -> CompanyFiscalDefault | None:
        return self._session.get(CompanyFiscalDefault, company_id)

    def add(self, fiscal_default: CompanyFiscalDefault) -> CompanyFiscalDefault:
        self._session.add(fiscal_default)
        return fiscal_default

    def save(self, fiscal_default: CompanyFiscalDefault) -> CompanyFiscalDefault:
        self._session.add(fiscal_default)
        return fiscal_default
