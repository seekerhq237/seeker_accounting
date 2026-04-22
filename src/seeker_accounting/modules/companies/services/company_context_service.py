from __future__ import annotations

from typing import Callable

from seeker_accounting.app.context.app_context import AppContext
from sqlalchemy.orm import Session

from seeker_accounting.app.context.active_company_context import ActiveCompanyContext
from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.repositories.user_company_access_repository import (
    UserCompanyAccessRepository,
)
from seeker_accounting.modules.companies.dto.company_dto import ActiveCompanyDTO
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.platform.exceptions import NotFoundError, PermissionDeniedError, ValidationError

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
UserCompanyAccessRepositoryFactory = Callable[[Session], UserCompanyAccessRepository]


class CompanyContextService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        app_context: AppContext,
        active_company_context: ActiveCompanyContext,
        company_repository_factory: CompanyRepositoryFactory,
        user_company_access_repository_factory: UserCompanyAccessRepositoryFactory,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._app_context = app_context
        self._active_company_context = active_company_context
        self._company_repository_factory = company_repository_factory
        self._user_company_access_repository_factory = user_company_access_repository_factory

    def set_active_company(self, company_id: int, user_id: int | None = None) -> ActiveCompanyDTO:
        with self._unit_of_work_factory() as uow:
            if uow.session is None:
                raise RuntimeError("Unit of work has no active session.")

            company_repository = self._company_repository_factory(uow.session)
            company = company_repository.get_by_id(company_id)
            if company is None:
                raise NotFoundError(f"Company with id {company_id} was not found.")
            if not company.is_active:
                raise ValidationError("Inactive companies cannot be activated.")

            self._ensure_company_access(company_id=company_id, user_id=user_id)
            active_company = ActiveCompanyDTO(
                company_id=company.id,
                company_name=company.display_name,
                base_currency_code=company.base_currency_code,
                logo_storage_path=company.logo_storage_path,
            )

        self._active_company_context.set_active_company(
            active_company.company_id,
            active_company.company_name,
            active_company.base_currency_code,
            active_company.logo_storage_path,
        )
        return active_company

    def get_active_company(self) -> ActiveCompanyDTO | None:
        company_id = self._active_company_context.company_id
        if company_id is None:
            return None

        company_name = self._active_company_context.company_name
        base_currency_code = self._active_company_context.base_currency_code
        if company_name and base_currency_code:
            return ActiveCompanyDTO(
                company_id=company_id,
                company_name=company_name,
                base_currency_code=base_currency_code,
                logo_storage_path=self._active_company_context.logo_storage_path,
            )

        with self._unit_of_work_factory() as uow:
            if uow.session is None:
                raise RuntimeError("Unit of work has no active session.")

            company_repository = self._company_repository_factory(uow.session)
            company = company_repository.get_by_id(company_id)
            if company is None or not company.is_active:
                self.clear_active_company()
                return None

            active_company = ActiveCompanyDTO(
                company_id=company.id,
                company_name=company.display_name,
                base_currency_code=company.base_currency_code,
                logo_storage_path=company.logo_storage_path,
            )

        self._active_company_context.set_active_company(
            active_company.company_id,
            active_company.company_name,
            active_company.base_currency_code,
            active_company.logo_storage_path,
        )
        return active_company

    def clear_active_company(self) -> None:
        self._active_company_context.clear_active_company()

    def _ensure_company_access(self, company_id: int, user_id: int | None) -> None:
        resolved_user_id = user_id if user_id is not None else self._app_context.current_user_id
        if resolved_user_id is None:
            return

        if resolved_user_id <= 0 or company_id <= 0:
            raise PermissionDeniedError("You do not have access to this company.")

        with self._unit_of_work_factory() as uow:
            if uow.session is None:
                raise RuntimeError("Unit of work has no active session.")
            access_repository = self._user_company_access_repository_factory(uow.session)
            access = access_repository.get_by_user_and_company(resolved_user_id, company_id)
            if access is None:
                raise PermissionDeniedError("You do not have access to this company.")
