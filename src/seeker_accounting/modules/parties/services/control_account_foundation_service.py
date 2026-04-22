from __future__ import annotations

from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.accounting.chart_of_accounts.models.account import Account
from seeker_accounting.modules.accounting.chart_of_accounts.repositories.account_repository import (
    AccountRepository,
)
from seeker_accounting.modules.accounting.reference_data.constants.account_role_codes import (
    ACCOUNT_ROLE_DEFINITION_BY_CODE,
)
from seeker_accounting.modules.accounting.reference_data.repositories.account_role_mapping_repository import (
    AccountRoleMappingRepository,
)
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.parties.dto.control_account_foundation_dto import (
    ControlAccountFoundationStatusDTO,
)
from seeker_accounting.platform.exceptions import NotFoundError

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
AccountRepositoryFactory = Callable[[Session], AccountRepository]
AccountRoleMappingRepositoryFactory = Callable[[Session], AccountRoleMappingRepository]


class ControlAccountFoundationService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        account_repository_factory: AccountRepositoryFactory,
        account_role_mapping_repository_factory: AccountRoleMappingRepositoryFactory,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory
        self._account_repository_factory = account_repository_factory
        self._account_role_mapping_repository_factory = account_role_mapping_repository_factory

    def get_customer_ar_foundation_status(self, company_id: int) -> ControlAccountFoundationStatusDTO:
        return self._get_foundation_status(company_id, "ar_control")

    def get_supplier_ap_foundation_status(self, company_id: int) -> ControlAccountFoundationStatusDTO:
        return self._get_foundation_status(company_id, "ap_control")

    def _get_foundation_status(self, company_id: int, role_code: str) -> ControlAccountFoundationStatusDTO:
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            account_repository = self._require_account_repository(uow.session)
            mapping_repository = self._require_mapping_repository(uow.session)

            mapping = mapping_repository.get_by_role_code(company_id, role_code)
            if mapping is None:
                return self._build_status(role_code, None, ("Required account role mapping is missing.",))

            account = account_repository.get_by_id(company_id, mapping.account_id)
            if account is None:
                return self._build_status(role_code, None, ("Mapped account no longer exists in this company.",))

            issues: list[str] = []
            if not account.is_active:
                issues.append("Mapped account is inactive.")
            if not account.is_control_account:
                issues.append("Mapped account is not marked as a control account.")
            return self._build_status(role_code, account, tuple(issues))

    def _require_company_exists(self, session: Session | None, company_id: int) -> None:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        repository = self._company_repository_factory(session)
        if repository.get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

    def _require_account_repository(self, session: Session | None) -> AccountRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._account_repository_factory(session)

    def _require_mapping_repository(self, session: Session | None) -> AccountRoleMappingRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._account_role_mapping_repository_factory(session)

    def _build_status(
        self,
        role_code: str,
        account: Account | None,
        issues: tuple[str, ...],
    ) -> ControlAccountFoundationStatusDTO:
        definition = ACCOUNT_ROLE_DEFINITION_BY_CODE[role_code]
        return ControlAccountFoundationStatusDTO(
            role_code=definition.role_code,
            role_label=definition.label,
            is_ready=not issues,
            mapped_account_id=account.id if account is not None else None,
            mapped_account_code=account.account_code if account is not None else None,
            mapped_account_name=account.account_name if account is not None else None,
            issues=issues,
        )
