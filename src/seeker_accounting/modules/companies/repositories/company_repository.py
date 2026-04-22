from __future__ import annotations

from datetime import datetime

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.companies.models.company import Company



class CompanyRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_all(self) -> list[Company]:
        statement = select(Company).order_by(Company.display_name.asc(), Company.legal_name.asc(), Company.id.asc())
        return list(self._session.scalars(statement))

    def list_active(self) -> list[Company]:
        statement = (
            select(Company)
            .where(Company.is_active == True)  # noqa: E712
            .order_by(Company.display_name.asc(), Company.legal_name.asc(), Company.id.asc())
        )
        return list(self._session.scalars(statement))

    def get_by_id(self, company_id: int) -> Company | None:
        return self._session.get(Company, company_id)

    def get_by_legal_name(self, legal_name: str) -> Company | None:
        return self._session.scalar(select(Company).where(Company.legal_name == legal_name))

    def get_by_display_name(self, display_name: str) -> Company | None:
        return self._session.scalar(select(Company).where(Company.display_name == display_name))

    def add(self, company: Company) -> Company:
        self._session.add(company)
        return company

    def save(self, company: Company) -> Company:
        self._session.add(company)
        return company

    def set_logo_metadata(
        self,
        company: Company,
        *,
        storage_path: str,
        original_filename: str,
        content_type: str,
        sha256: str,
        updated_at: datetime,
    ) -> Company:
        company.logo_storage_path = storage_path
        company.logo_original_filename = original_filename
        company.logo_content_type = content_type
        company.logo_sha256 = sha256
        company.logo_updated_at = updated_at
        self._session.add(company)
        return company

    def clear_logo_metadata(self, company: Company) -> Company:
        company.logo_storage_path = None
        company.logo_original_filename = None
        company.logo_content_type = None
        company.logo_sha256 = None
        company.logo_updated_at = None
        self._session.add(company)
        return company

    def legal_name_exists(self, legal_name: str, exclude_company_id: int | None = None) -> bool:
        predicate = Company.legal_name == legal_name
        if exclude_company_id is not None:
            predicate = predicate & (Company.id != exclude_company_id)
        return bool(self._session.scalar(select(exists().where(predicate))))

    def display_name_exists(self, display_name: str, exclude_company_id: int | None = None) -> bool:
        predicate = Company.display_name == display_name
        if exclude_company_id is not None:
            predicate = predicate & (Company.id != exclude_company_id)
        return bool(self._session.scalar(select(exists().where(predicate))))

    def list_all_for_admin(self) -> list[Company]:
        """Return ALL companies regardless of is_active or deleted_at status (admin-only use)."""
        statement = select(Company).order_by(Company.display_name.asc(), Company.legal_name.asc(), Company.id.asc())
        return list(self._session.scalars(statement))

    def list_pending_deletion_before(self, cutoff: datetime) -> list[Company]:
        """Return companies scheduled for deletion whose deleted_at timestamp is on or before the cutoff."""
        statement = (
            select(Company)
            .where(Company.deleted_at.is_not(None))  # type: ignore[attr-defined]
            .where(Company.deleted_at <= cutoff)
            .order_by(Company.deleted_at.asc())
        )
        return list(self._session.scalars(statement))
