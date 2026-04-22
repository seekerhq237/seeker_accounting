from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.accounting.chart_of_accounts.repositories.account_repository import AccountRepository
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.contracts_projects.dto.project_cost_code_commands import (
    CreateProjectCostCodeCommand,
    UpdateProjectCostCodeCommand,
)
from seeker_accounting.modules.contracts_projects.dto.project_cost_code_dto import (
    ProjectCostCodeDetailDTO,
    ProjectCostCodeListItemDTO,
)
from seeker_accounting.modules.contracts_projects.models.project_cost_code import ProjectCostCode
from seeker_accounting.modules.contracts_projects.repositories.project_cost_code_repository import (
    ProjectCostCodeRepository,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

ProjectCostCodeRepositoryFactory = Callable[[Session], ProjectCostCodeRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
AccountRepositoryFactory = Callable[[Session], AccountRepository]

_VALID_COST_CODE_TYPES = frozenset({
    "labour",
    "materials",
    "equipment",
    "subcontract",
    "overhead",
    "other",
})


class ProjectCostCodeService:
    """Manage company-level project cost codes."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        project_cost_code_repository_factory: ProjectCostCodeRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        account_repository_factory: AccountRepositoryFactory,
        audit_service: "AuditService | None" = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._project_cost_code_repository_factory = project_cost_code_repository_factory
        self._company_repository_factory = company_repository_factory
        self._account_repository_factory = account_repository_factory
        self._audit_service = audit_service

    def create_cost_code(self, command: CreateProjectCostCodeCommand) -> ProjectCostCodeDetailDTO:
        if not command.code or not command.code.strip():
            raise ValidationError("Cost code is required.")
        if not command.name or not command.name.strip():
            raise ValidationError("Cost code name is required.")
        if command.cost_code_type_code not in _VALID_COST_CODE_TYPES:
            raise ValidationError(
                f"Invalid cost code type: {command.cost_code_type_code}. "
                f"Valid: {', '.join(sorted(_VALID_COST_CODE_TYPES))}."
            )

        with self._unit_of_work_factory() as uow:
            if self._company_repository_factory(uow.session).get_by_id(command.company_id) is None:
                raise NotFoundError(f"Company {command.company_id} not found.")

            repo = self._project_cost_code_repository_factory(uow.session)

            existing = repo.get_by_company_and_code(command.company_id, command.code.strip())
            if existing is not None:
                raise ConflictError(f"Cost code '{command.code}' already exists for this company.")

            if command.default_account_id is not None:
                account = self._account_repository_factory(uow.session).get_by_id(command.company_id, command.default_account_id)
                if account is None:
                    raise NotFoundError(f"Account {command.default_account_id} not found.")

            cost_code = ProjectCostCode(
                company_id=command.company_id,
                code=command.code.strip(),
                name=command.name.strip(),
                cost_code_type_code=command.cost_code_type_code,
                default_account_id=command.default_account_id,
                description=command.description,
                is_active=True,
            )
            repo.add(cost_code)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Cost code could not be created.") from exc

            from seeker_accounting.modules.audit.event_type_catalog import PROJECT_COST_CODE_CREATED
            self._record_audit(command.company_id, PROJECT_COST_CODE_CREATED, "ProjectCostCode", cost_code.id, f"Created cost code '{command.code}'")
            return self._to_detail_dto(cost_code, uow.session)

    def update_cost_code(self, cost_code_id: int, command: UpdateProjectCostCodeCommand) -> ProjectCostCodeDetailDTO:
        if not command.name or not command.name.strip():
            raise ValidationError("Cost code name is required.")
        if command.cost_code_type_code not in _VALID_COST_CODE_TYPES:
            raise ValidationError(
                f"Invalid cost code type: {command.cost_code_type_code}. "
                f"Valid: {', '.join(sorted(_VALID_COST_CODE_TYPES))}."
            )

        with self._unit_of_work_factory() as uow:
            repo = self._project_cost_code_repository_factory(uow.session)
            cost_code = repo.get_by_id(cost_code_id)
            if cost_code is None:
                raise NotFoundError(f"Cost code {cost_code_id} not found.")

            if command.default_account_id is not None:
                account = self._account_repository_factory(uow.session).get_by_id(cost_code.company_id, command.default_account_id)
                if account is None:
                    raise NotFoundError(f"Account {command.default_account_id} not found.")

            cost_code.name = command.name.strip()
            cost_code.cost_code_type_code = command.cost_code_type_code
            cost_code.default_account_id = command.default_account_id
            cost_code.description = command.description
            repo.save(cost_code)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Cost code could not be updated.") from exc

            from seeker_accounting.modules.audit.event_type_catalog import PROJECT_COST_CODE_UPDATED
            self._record_audit(cost_code.company_id, PROJECT_COST_CODE_UPDATED, "ProjectCostCode", cost_code.id, f"Updated cost code id={cost_code_id}")
            return self._to_detail_dto(cost_code, uow.session)

    def get_cost_code_detail(self, cost_code_id: int) -> ProjectCostCodeDetailDTO:
        with self._unit_of_work_factory() as uow:
            repo = self._project_cost_code_repository_factory(uow.session)
            cost_code = repo.get_by_id(cost_code_id)
            if cost_code is None:
                raise NotFoundError(f"Cost code {cost_code_id} not found.")
            return self._to_detail_dto(cost_code, uow.session)

    def list_cost_codes(self, company_id: int, active_only: bool = False) -> list[ProjectCostCodeListItemDTO]:
        with self._unit_of_work_factory() as uow:
            repo = self._project_cost_code_repository_factory(uow.session)
            cost_codes = repo.list_by_company(company_id, active_only=active_only)
            return [self._to_list_item_dto(cc, uow.session) for cc in cost_codes]

    def deactivate_cost_code(self, cost_code_id: int) -> ProjectCostCodeDetailDTO:
        with self._unit_of_work_factory() as uow:
            repo = self._project_cost_code_repository_factory(uow.session)
            cost_code = repo.get_by_id(cost_code_id)
            if cost_code is None:
                raise NotFoundError(f"Cost code {cost_code_id} not found.")
            if not cost_code.is_active:
                raise ValidationError("Cost code is already inactive.")
            cost_code.is_active = False
            repo.save(cost_code)
            uow.commit()
            from seeker_accounting.modules.audit.event_type_catalog import PROJECT_COST_CODE_DEACTIVATED
            self._record_audit(cost_code.company_id, PROJECT_COST_CODE_DEACTIVATED, "ProjectCostCode", cost_code.id, f"Deactivated cost code id={cost_code_id}")
            return self._to_detail_dto(cost_code, uow.session)

    def reactivate_cost_code(self, cost_code_id: int) -> ProjectCostCodeDetailDTO:
        with self._unit_of_work_factory() as uow:
            repo = self._project_cost_code_repository_factory(uow.session)
            cost_code = repo.get_by_id(cost_code_id)
            if cost_code is None:
                raise NotFoundError(f"Cost code {cost_code_id} not found.")
            if cost_code.is_active:
                raise ValidationError("Cost code is already active.")
            cost_code.is_active = True
            repo.save(cost_code)
            uow.commit()
            from seeker_accounting.modules.audit.event_type_catalog import PROJECT_COST_CODE_UPDATED
            self._record_audit(cost_code.company_id, PROJECT_COST_CODE_UPDATED, "ProjectCostCode", cost_code.id, f"Reactivated cost code id={cost_code_id}")
            return self._to_detail_dto(cost_code, uow.session)

    def _to_list_item_dto(self, cc: ProjectCostCode, session: Session) -> ProjectCostCodeListItemDTO:
        default_account_code = None
        if cc.default_account_id is not None:
            account = self._account_repository_factory(session).get_by_id(cc.company_id, cc.default_account_id)
            default_account_code = account.account_code if account else None

        return ProjectCostCodeListItemDTO(
            id=cc.id,
            code=cc.code,
            name=cc.name,
            cost_code_type_code=cc.cost_code_type_code,
            default_account_code=default_account_code,
            is_active=cc.is_active,
            updated_at=cc.updated_at,
        )

    def _to_detail_dto(self, cc: ProjectCostCode, session: Session) -> ProjectCostCodeDetailDTO:
        default_account_code = None
        if cc.default_account_id is not None:
            account = self._account_repository_factory(session).get_by_id(cc.company_id, cc.default_account_id)
            default_account_code = account.account_code if account else None

        return ProjectCostCodeDetailDTO(
            id=cc.id,
            company_id=cc.company_id,
            code=cc.code,
            name=cc.name,
            cost_code_type_code=cc.cost_code_type_code,
            default_account_id=cc.default_account_id,
            default_account_code=default_account_code,
            is_active=cc.is_active,
            description=cc.description,
            created_at=cc.created_at,
            updated_at=cc.updated_at,
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
        from seeker_accounting.modules.audit.event_type_catalog import MODULE_CONTRACTS
        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type_code,
                    module_code=MODULE_CONTRACTS,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    description=description,
                ),
            )
        except Exception:
            pass  # Audit must not break business operations
