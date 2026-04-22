from __future__ import annotations

from sqlalchemy.orm import Session

from seeker_accounting.modules.reporting.models.ias_income_statement_preference import (
    IasIncomeStatementPreference,
)


class IasIncomeStatementPreferenceRepository:
    """Company-scoped IAS template preference persistence."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_company_id(self, company_id: int) -> IasIncomeStatementPreference | None:
        return self._session.get(IasIncomeStatementPreference, company_id)

    def add(self, preference: IasIncomeStatementPreference) -> IasIncomeStatementPreference:
        self._session.add(preference)
        return preference

    def save(self, preference: IasIncomeStatementPreference) -> IasIncomeStatementPreference:
        self._session.add(preference)
        return preference
