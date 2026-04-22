from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.accounting.chart_of_accounts.models.account import Account
from seeker_accounting.modules.accounting.chart_of_accounts.repositories.account_repository import (
    AccountRepository,
)
from seeker_accounting.modules.accounting.reference_data.constants.account_role_codes import (
    ACCOUNT_ROLE_DEFINITION_BY_CODE,
    ACCOUNT_ROLE_DEFINITIONS,
)
from seeker_accounting.modules.accounting.reference_data.dto.account_role_mapping_dto import (
    AccountRoleMappingDTO,
    AccountRoleOptionDTO,
    SetAccountRoleMappingCommand,
)
from seeker_accounting.modules.accounting.reference_data.models.account_role_mapping import (
    AccountRoleMapping,
)
from seeker_accounting.modules.accounting.reference_data.repositories.account_role_mapping_repository import (
    AccountRoleMappingRepository,
)
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

AccountRepositoryFactory = Callable[[Session], AccountRepository]
AccountRoleMappingRepositoryFactory = Callable[[Session], AccountRoleMappingRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]


class AccountRoleMappingService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        account_repository_factory: AccountRepositoryFactory,
        account_role_mapping_repository_factory: AccountRoleMappingRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        permission_service: PermissionService,
        audit_service: "AuditService | None" = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._account_repository_factory = account_repository_factory
        self._account_role_mapping_repository_factory = account_role_mapping_repository_factory
        self._company_repository_factory = company_repository_factory
        self._permission_service = permission_service
        self._audit_service = audit_service

    def list_role_options(self) -> list[AccountRoleOptionDTO]:
        return [
            AccountRoleOptionDTO(
                role_code=definition.role_code,
                label=definition.label,
                description=definition.description,
            )
            for definition in ACCOUNT_ROLE_DEFINITIONS
        ]

    def list_role_mappings(self, company_id: int) -> list[AccountRoleMappingDTO]:
        self._permission_service.require_any_permission(
            ("reference.account_role_mappings.view", "chart.role_mappings.view")
        )
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            account_repository = self._require_account_repository(uow.session)
            mapping_repository = self._require_mapping_repository(uow.session)

            accounts_by_id = {
                account.id: account
                for account in account_repository.list_by_company(company_id, active_only=False)
            }
            mappings_by_role_code = {
                mapping.role_code: mapping
                for mapping in mapping_repository.list_by_company(company_id)
            }

            return [
                self._to_mapping_dto(
                    role_code=definition.role_code,
                    mapping=mappings_by_role_code.get(definition.role_code),
                    account=accounts_by_id.get(mappings_by_role_code[definition.role_code].account_id)
                    if definition.role_code in mappings_by_role_code
                    else None,
                )
                for definition in ACCOUNT_ROLE_DEFINITIONS
            ]

    def set_role_mapping(self, company_id: int, command: SetAccountRoleMappingCommand) -> AccountRoleMappingDTO:
        self._permission_service.require_any_permission(
            ("reference.account_role_mappings.manage", "chart.role_mappings.manage")
        )
        normalized_role_code = self._require_role_code(command.role_code)

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            account_repository = self._require_account_repository(uow.session)
            mapping_repository = self._require_mapping_repository(uow.session)

            account = account_repository.get_by_id(company_id, command.account_id)
            if account is None:
                raise ValidationError("Mapped account must belong to the active company.")

            mapping = mapping_repository.get_by_role_code(company_id, normalized_role_code)
            if mapping is None:
                mapping = AccountRoleMapping(
                    company_id=company_id,
                    role_code=normalized_role_code,
                    account_id=account.id,
                )
                mapping_repository.add(mapping)
            else:
                mapping.account_id = account.id
                mapping_repository.save(mapping)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Account role mapping could not be saved.") from exc

            from seeker_accounting.modules.audit.event_type_catalog import ACCOUNT_ROLE_MAPPING_SET
            self._record_audit(company_id, ACCOUNT_ROLE_MAPPING_SET, "AccountRoleMapping", mapping.id, f"Set account role mapping for role '{normalized_role_code}'")
            return self._to_mapping_dto(role_code=normalized_role_code, mapping=mapping, account=account)

    def clear_role_mapping(self, company_id: int, role_code: str) -> None:
        self._permission_service.require_any_permission(
            ("reference.account_role_mappings.manage", "chart.role_mappings.manage")
        )
        normalized_role_code = self._require_role_code(role_code)

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            mapping_repository = self._require_mapping_repository(uow.session)
            mapping = mapping_repository.get_by_role_code(company_id, normalized_role_code)
            if mapping is None:
                return

            mapping_repository.delete(mapping)
            uow.commit()
            from seeker_accounting.modules.audit.event_type_catalog import ACCOUNT_ROLE_MAPPING_CLEARED
            self._record_audit(company_id, ACCOUNT_ROLE_MAPPING_CLEARED, "AccountRoleMapping", mapping.id, f"Cleared account role mapping for role '{normalized_role_code}'")

    def _require_company_exists(self, session: Session | None, company_id: int) -> None:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        company_repository = self._company_repository_factory(session)
        if company_repository.get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

    def _require_account_repository(self, session: Session | None) -> AccountRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._account_repository_factory(session)

    def _require_mapping_repository(self, session: Session | None) -> AccountRoleMappingRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._account_role_mapping_repository_factory(session)

    def _require_role_code(self, role_code: str) -> str:
        normalized = role_code.strip().lower()
        if not normalized:
            raise ValidationError("Role code is required.")
        if normalized not in ACCOUNT_ROLE_DEFINITION_BY_CODE:
            raise ValidationError("Role code is not recognized.")
        return normalized

    def _to_mapping_dto(
        self,
        *,
        role_code: str,
        mapping: AccountRoleMapping | None,
        account: Account | None,
    ) -> AccountRoleMappingDTO:
        role_definition = ACCOUNT_ROLE_DEFINITION_BY_CODE[role_code]
        return AccountRoleMappingDTO(
            role_code=role_definition.role_code,
            role_label=role_definition.label,
            account_id=account.id if account is not None else None,
            account_code=account.account_code if account is not None else None,
            account_name=account.account_name if account is not None else None,
            updated_at=mapping.updated_at if mapping is not None else None,
        )

    def _record_audit(
        self,
        company_id: int,
        event_type_code: str,
        entity_type: str,
        entity_id: int | None,
        description: str,
    ) -> None:
        if self._audit_service is None:
            return
        from seeker_accounting.modules.audit.dto.audit_event_dto import RecordAuditEventCommand
        from seeker_accounting.modules.audit.event_type_catalog import MODULE_REFERENCE
        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type_code,
                    module_code=MODULE_REFERENCE,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    description=description,
                ),
            )
        except Exception:
            pass  # Audit must not break business operations
