"""Repository for ``CompanyTaxProfile``."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.taxation.models.company_tax_profile import (
    CompanyTaxProfile,
)


class CompanyTaxProfileRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_company(self, company_id: int) -> CompanyTaxProfile | None:
        statement = select(CompanyTaxProfile).where(
            CompanyTaxProfile.company_id == company_id,
        )
        return self._session.scalar(statement)

    def add(self, profile: CompanyTaxProfile) -> CompanyTaxProfile:
        self._session.add(profile)
        return profile

    def save(self, profile: CompanyTaxProfile) -> CompanyTaxProfile:
        self._session.add(profile)
        return profile
