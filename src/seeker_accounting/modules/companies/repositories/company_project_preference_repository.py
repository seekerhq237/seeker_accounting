from __future__ import annotations

from sqlalchemy.orm import Session

from seeker_accounting.modules.companies.models.company_project_preference import CompanyProjectPreference


class CompanyProjectPreferenceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_company_id(self, company_id: int) -> CompanyProjectPreference | None:
        return self._session.get(CompanyProjectPreference, company_id)

    def add(self, preference: CompanyProjectPreference) -> CompanyProjectPreference:
        self._session.add(preference)
        return preference

    def save(self, preference: CompanyProjectPreference) -> CompanyProjectPreference:
        self._session.add(preference)
        return preference