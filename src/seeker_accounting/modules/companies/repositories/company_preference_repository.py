from __future__ import annotations

from sqlalchemy.orm import Session

from seeker_accounting.modules.companies.models.company_preference import CompanyPreference


class CompanyPreferenceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_company_id(self, company_id: int) -> CompanyPreference | None:
        return self._session.get(CompanyPreference, company_id)

    def add(self, preference: CompanyPreference) -> CompanyPreference:
        self._session.add(preference)
        return preference

    def save(self, preference: CompanyPreference) -> CompanyPreference:
        self._session.add(preference)
        return preference
