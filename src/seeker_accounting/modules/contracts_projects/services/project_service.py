from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.accounting.reference_data.repositories.currency_repository import CurrencyRepository
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.contracts_projects.dto.project_dto import (
    CreateProjectCommand,
    ProjectDetailDTO,
    ProjectListItemDTO,
    UpdateProjectCommand,
)
from seeker_accounting.modules.contracts_projects.models.project import Project
from seeker_accounting.modules.contracts_projects.repositories.contract_repository import ContractRepository
from seeker_accounting.modules.contracts_projects.repositories.project_repository import ProjectRepository
from seeker_accounting.modules.customers.repositories.customer_repository import CustomerRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

ProjectRepositoryFactory = Callable[[Session], ProjectRepository]
ContractRepositoryFactory = Callable[[Session], ContractRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
CustomerRepositoryFactory = Callable[[Session], CustomerRepository]
CurrencyRepositoryFactory = Callable[[Session], CurrencyRepository]

_VALID_PROJECT_TYPES = frozenset({
    "external",
    "internal",
    "capital",
    "administrative",
    "other",
})

_VALID_PROJECT_STATUSES = frozenset({
    "draft",
    "active",
    "on_hold",
    "completed",
    "closed",
    "cancelled",
})

_VALID_BUDGET_CONTROL_MODES = frozenset({
    "none",
    "warn",
    "hard_stop",
})


class ProjectService:
    """Manage projects."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        project_repository_factory: ProjectRepositoryFactory,
        contract_repository_factory: ContractRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        customer_repository_factory: CustomerRepositoryFactory,
        currency_repository_factory: CurrencyRepositoryFactory,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._project_repository_factory = project_repository_factory
        self._contract_repository_factory = contract_repository_factory
        self._company_repository_factory = company_repository_factory
        self._customer_repository_factory = customer_repository_factory
        self._currency_repository_factory = currency_repository_factory
        self._audit_service = audit_service

    def create_project(self, command: CreateProjectCommand) -> ProjectDetailDTO:
        self._validate_create_command(command)

        with self._unit_of_work_factory() as uow:
            self._validate_dependencies(uow.session, command=command)
            repository = self._project_repository_factory(uow.session)

            project = Project(
                company_id=command.company_id,
                project_code=command.project_code,
                project_name=command.project_name,
                contract_id=command.contract_id,
                customer_id=command.customer_id,
                project_type_code=command.project_type_code,
                project_manager_user_id=command.project_manager_user_id,
                currency_code=command.currency_code,
                exchange_rate=command.exchange_rate,
                start_date=command.start_date,
                planned_end_date=command.planned_end_date,
                status_code="draft",
                budget_control_mode_code=command.budget_control_mode_code,
                notes=command.notes,
                created_by_user_id=command.created_by_user_id,
            )
            repository.add(project)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Project could not be created.") from exc

            from seeker_accounting.modules.audit.event_type_catalog import PROJECT_CREATED
            self._record_audit(command.company_id, PROJECT_CREATED, "Project", project.id, "Created project")
            return self._to_detail_dto(project, uow.session)

    def update_project(self, project_id: int, command: UpdateProjectCommand) -> ProjectDetailDTO:
        self._validate_update_command(command)

        with self._unit_of_work_factory() as uow:
            repository = self._project_repository_factory(uow.session)
            project = repository.get_by_id(project_id)
            if project is None:
                raise NotFoundError(f"Project {project_id} not found.")

            self._validate_dependencies(uow.session, command=command, project=project)

            project.project_name = command.project_name
            project.contract_id = command.contract_id
            project.customer_id = command.customer_id
            project.project_type_code = command.project_type_code
            project.project_manager_user_id = command.project_manager_user_id
            project.currency_code = command.currency_code
            project.exchange_rate = command.exchange_rate
            project.start_date = command.start_date
            project.planned_end_date = command.planned_end_date
            project.budget_control_mode_code = command.budget_control_mode_code
            project.notes = command.notes
            project.updated_by_user_id = command.updated_by_user_id

            repository.save(project)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Project could not be updated.") from exc

            from seeker_accounting.modules.audit.event_type_catalog import PROJECT_UPDATED
            self._record_audit(command.company_id, PROJECT_UPDATED, "Project", project.id, "Updated project")
            return self._to_detail_dto(project, uow.session)

    def get_project_detail(self, project_id: int) -> ProjectDetailDTO:
        with self._unit_of_work_factory() as uow:
            repository = self._project_repository_factory(uow.session)
            project = repository.get_by_id(project_id)
            if project is None:
                raise NotFoundError(f"Project {project_id} not found.")
            return self._to_detail_dto(project, uow.session)

    def list_projects(self, company_id: int) -> list[ProjectListItemDTO]:
        with self._unit_of_work_factory() as uow:
            repository = self._project_repository_factory(uow.session)
            projects = repository.list_by_company(company_id)
            return [self._to_list_item_dto(project, uow.session) for project in projects]

    def activate_project(self, project_id: int) -> ProjectDetailDTO:
        return self._change_status(project_id, "active", ["draft", "on_hold"])

    def put_project_on_hold(self, project_id: int) -> ProjectDetailDTO:
        return self._change_status(project_id, "on_hold", ["active"])

    def complete_project(self, project_id: int) -> ProjectDetailDTO:
        return self._change_status(project_id, "completed", ["active", "on_hold"])

    def close_project(self, project_id: int) -> ProjectDetailDTO:
        return self._change_status(project_id, "closed", ["completed"])

    def cancel_project(self, project_id: int) -> ProjectDetailDTO:
        return self._change_status(project_id, "cancelled", ["draft", "active", "on_hold"])

    def _change_status(self, project_id: int, new_status: str, allowed_from: list[str]) -> ProjectDetailDTO:
        with self._unit_of_work_factory() as uow:
            repository = self._project_repository_factory(uow.session)
            project = repository.get_by_id(project_id)
            if project is None:
                raise NotFoundError(f"Project {project_id} not found.")

            if project.status_code not in allowed_from:
                raise ValidationError(
                    f"Cannot change project status from '{project.status_code}' to '{new_status}'."
                )

            project.status_code = new_status
            repository.save(project)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Project status could not be updated.") from exc

            return self._to_detail_dto(project, uow.session)

    def _validate_create_command(self, command: CreateProjectCommand) -> None:
        if command.project_type_code not in _VALID_PROJECT_TYPES:
            raise ValidationError(
                f"Invalid project type: {command.project_type_code}. "
                f"Valid: {', '.join(sorted(_VALID_PROJECT_TYPES))}."
            )
        if command.budget_control_mode_code is not None and command.budget_control_mode_code not in _VALID_BUDGET_CONTROL_MODES:
            raise ValidationError(
                f"Invalid budget control mode: {command.budget_control_mode_code}. "
                f"Valid: {', '.join(sorted(_VALID_BUDGET_CONTROL_MODES))}."
            )
        if command.start_date and command.planned_end_date and command.start_date > command.planned_end_date:
            raise ValidationError("Start date cannot be after planned end date.")

    def _validate_update_command(self, command: UpdateProjectCommand) -> None:
        if command.project_type_code not in _VALID_PROJECT_TYPES:
            raise ValidationError(
                f"Invalid project type: {command.project_type_code}. "
                f"Valid: {', '.join(sorted(_VALID_PROJECT_TYPES))}."
            )
        if command.budget_control_mode_code is not None and command.budget_control_mode_code not in _VALID_BUDGET_CONTROL_MODES:
            raise ValidationError(
                f"Invalid budget control mode: {command.budget_control_mode_code}. "
                f"Valid: {', '.join(sorted(_VALID_BUDGET_CONTROL_MODES))}."
            )
        if command.start_date and command.planned_end_date and command.start_date > command.planned_end_date:
            raise ValidationError("Start date cannot be after planned end date.")

    def _validate_dependencies(self, session: Session, command: CreateProjectCommand | UpdateProjectCommand | None = None, project: Project | None = None) -> None:
        company_id = command.company_id if command is not None else project.company_id
        contract_id = command.contract_id if command is not None else project.contract_id
        customer_id = command.customer_id if command is not None else project.customer_id
        currency_code = command.currency_code if command is not None else project.currency_code

        if self._company_repository_factory(session).get_by_id(company_id) is None:
            raise NotFoundError(f"Company {company_id} not found.")

        if contract_id is not None:
            contract = self._contract_repository_factory(session).get_by_id(contract_id)
            if contract is None:
                raise NotFoundError(f"Contract {contract_id} not found.")
            if contract.company_id != company_id:
                raise ValidationError("Contract does not belong to the specified company.")

        if customer_id is not None:
            customer = self._customer_repository_factory(session).get_by_id(company_id, customer_id)
            if customer is None:
                raise NotFoundError(f"Customer {customer_id} not found.")

        if contract_id is not None and customer_id is not None:
            contract = self._contract_repository_factory(session).get_by_id(contract_id)
            if contract is not None and contract.customer_id != customer_id:
                raise ValidationError("The project customer must match the contract customer.")

        if currency_code is not None and not self._currency_repository_factory(session).exists_active(currency_code):
            raise ValidationError(f"Currency code {currency_code} is not found or not active.")

    def _to_list_item_dto(self, project: Project, session: Session) -> ProjectListItemDTO:
        contract_number = None
        if project.contract_id:
            contract = self._contract_repository_factory(session).get_by_id(project.contract_id)
            contract_number = contract.contract_number if contract else None

        customer_display_name = None
        if project.customer_id:
            customer = self._customer_repository_factory(session).get_by_id(project.company_id, project.customer_id)
            customer_display_name = customer.display_name if customer else None

        project_manager_display_name = None
        if project.project_manager_user_id:
            # Assuming we have a way to get user, but for now skip
            pass

        return ProjectListItemDTO(
            id=project.id,
            project_code=project.project_code,
            project_name=project.project_name,
            contract_number=contract_number,
            customer_display_name=customer_display_name,
            project_type_code=project.project_type_code,
            status_code=project.status_code,
            start_date=project.start_date,
            planned_end_date=project.planned_end_date,
            project_manager_display_name=project_manager_display_name,
            updated_at=project.updated_at,
        )

    def _to_detail_dto(self, project: Project, session: Session) -> ProjectDetailDTO:
        contract_number = None
        if project.contract_id:
            contract = self._contract_repository_factory(session).get_by_id(project.contract_id)
            contract_number = contract.contract_number if contract else None

        customer_display_name = None
        if project.customer_id:
            customer = self._customer_repository_factory(session).get_by_id(project.company_id, project.customer_id)
            customer_display_name = customer.display_name if customer else None

        project_manager_display_name = None
        if project.project_manager_user_id:
            # Assuming we have a way to get user, but for now skip
            pass

        return ProjectDetailDTO(
            id=project.id,
            company_id=project.company_id,
            project_code=project.project_code,
            project_name=project.project_name,
            contract_id=project.contract_id,
            contract_number=contract_number,
            customer_id=project.customer_id,
            customer_display_name=customer_display_name,
            project_type_code=project.project_type_code,
            project_manager_user_id=project.project_manager_user_id,
            project_manager_display_name=project_manager_display_name,
            currency_code=project.currency_code,
            exchange_rate=project.exchange_rate,
            start_date=project.start_date,
            planned_end_date=project.planned_end_date,
            actual_end_date=project.actual_end_date,
            status_code=project.status_code,
            budget_control_mode_code=project.budget_control_mode_code,
            notes=project.notes,
            created_at=project.created_at,
            updated_at=project.updated_at,
            created_by_user_id=project.created_by_user_id,
            updated_by_user_id=project.updated_by_user_id,
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
