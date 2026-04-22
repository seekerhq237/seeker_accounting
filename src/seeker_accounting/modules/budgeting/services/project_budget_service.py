from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.budgeting.dto.project_budget_commands import (
    AddProjectBudgetLineCommand,
    CreateProjectBudgetVersionCommand,
    UpdateProjectBudgetLineCommand,
    UpdateProjectBudgetVersionCommand,
)
from seeker_accounting.modules.budgeting.dto.project_budget_dto import (
    ProjectBudgetLineDTO,
    ProjectBudgetVersionDetailDTO,
    ProjectBudgetVersionListItemDTO,
)
from seeker_accounting.modules.budgeting.models.project_budget_line import ProjectBudgetLine
from seeker_accounting.modules.budgeting.models.project_budget_version import ProjectBudgetVersion
from seeker_accounting.modules.budgeting.repositories.project_budget_line_repository import (
    ProjectBudgetLineRepository,
)
from seeker_accounting.modules.budgeting.repositories.project_budget_version_repository import (
    ProjectBudgetVersionRepository,
)
from seeker_accounting.modules.contracts_projects.repositories.project_job_repository import (
    ProjectJobRepository,
)
from seeker_accounting.modules.contracts_projects.repositories.project_repository import ProjectRepository
from seeker_accounting.modules.contracts_projects.repositories.project_cost_code_repository import (
    ProjectCostCodeRepository,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

ProjectBudgetVersionRepositoryFactory = Callable[[Session], ProjectBudgetVersionRepository]
ProjectBudgetLineRepositoryFactory = Callable[[Session], ProjectBudgetLineRepository]
ProjectRepositoryFactory = Callable[[Session], ProjectRepository]
ProjectJobRepositoryFactory = Callable[[Session], ProjectJobRepository]
ProjectCostCodeRepositoryFactory = Callable[[Session], ProjectCostCodeRepository]

_VALID_VERSION_TYPE_CODES = frozenset({"original", "revision", "working", "forecast"})
_VALID_STATUS_CODES = frozenset({"draft", "submitted", "approved", "superseded", "cancelled"})
_EDITABLE_STATUSES = frozenset({"draft", "submitted"})


class ProjectBudgetService:
    """Manage project budget versions and budget lines."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        version_repository_factory: ProjectBudgetVersionRepositoryFactory,
        line_repository_factory: ProjectBudgetLineRepositoryFactory,
        project_repository_factory: ProjectRepositoryFactory,
        project_job_repository_factory: ProjectJobRepositoryFactory,
        project_cost_code_repository_factory: ProjectCostCodeRepositoryFactory,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._version_repository_factory = version_repository_factory
        self._line_repository_factory = line_repository_factory
        self._project_repository_factory = project_repository_factory
        self._project_job_repository_factory = project_job_repository_factory
        self._project_cost_code_repository_factory = project_cost_code_repository_factory
        self._audit_service = audit_service

    # ── Version CRUD ─────────────────────────────────────────────────

    def create_version(self, command: CreateProjectBudgetVersionCommand) -> ProjectBudgetVersionDetailDTO:
        if not command.version_name or not command.version_name.strip():
            raise ValidationError("Version name is required.")
        if command.version_type_code not in _VALID_VERSION_TYPE_CODES:
            raise ValidationError(
                f"Invalid version type code '{command.version_type_code}'. "
                f"Must be one of: {', '.join(sorted(_VALID_VERSION_TYPE_CODES))}."
            )
        if command.version_number < 1:
            raise ValidationError("Version number must be at least 1.")

        with self._unit_of_work_factory() as uow:
            project_repo = self._project_repository_factory(uow.session)
            project = project_repo.get_by_id(command.project_id)
            if project is None:
                raise NotFoundError(f"Project {command.project_id} not found.")
            if project.company_id != command.company_id:
                raise ValidationError("Project does not belong to the specified company.")

            version_repo = self._version_repository_factory(uow.session)
            existing = version_repo.get_by_project_and_version_number(
                command.project_id, command.version_number
            )
            if existing is not None:
                raise ConflictError(
                    f"Version number {command.version_number} already exists for this project."
                )

            if command.base_version_id is not None:
                base = version_repo.get_by_id(command.base_version_id)
                if base is None:
                    raise NotFoundError(f"Base version {command.base_version_id} not found.")
                if base.project_id != command.project_id:
                    raise ValidationError("Base version does not belong to the same project.")

            version = ProjectBudgetVersion(
                company_id=command.company_id,
                project_id=command.project_id,
                version_number=command.version_number,
                version_name=command.version_name.strip(),
                version_type_code=command.version_type_code,
                status_code="draft",
                base_version_id=command.base_version_id,
                budget_date=command.budget_date,
                revision_reason=command.revision_reason,
                total_budget_amount=Decimal("0"),
            )
            version_repo.add(version)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Budget version could not be created.") from exc

            from seeker_accounting.modules.audit.event_type_catalog import BUDGET_VERSION_CREATED
            self._record_audit(command.company_id, BUDGET_VERSION_CREATED, "ProjectBudgetVersion", version.id, "Created budget version")
            return self._to_version_detail_dto(version)

    def update_version(
        self, version_id: int, command: UpdateProjectBudgetVersionCommand
    ) -> ProjectBudgetVersionDetailDTO:
        if not command.version_name or not command.version_name.strip():
            raise ValidationError("Version name is required.")
        if command.version_type_code not in _VALID_VERSION_TYPE_CODES:
            raise ValidationError(
                f"Invalid version type code '{command.version_type_code}'. "
                f"Must be one of: {', '.join(sorted(_VALID_VERSION_TYPE_CODES))}."
            )

        with self._unit_of_work_factory() as uow:
            version_repo = self._version_repository_factory(uow.session)
            version = version_repo.get_by_id(version_id)
            if version is None:
                raise NotFoundError(f"Budget version {version_id} not found.")
            if version.status_code not in _EDITABLE_STATUSES:
                raise ValidationError("Only draft or submitted budget versions can be edited.")

            if command.base_version_id is not None:
                if command.base_version_id == version_id:
                    raise ValidationError("A version cannot be its own base version.")
                base = version_repo.get_by_id(command.base_version_id)
                if base is None:
                    raise NotFoundError(f"Base version {command.base_version_id} not found.")
                if base.project_id != version.project_id:
                    raise ValidationError("Base version does not belong to the same project.")

            version.version_name = command.version_name.strip()
            version.version_type_code = command.version_type_code
            version.budget_date = command.budget_date
            version.base_version_id = command.base_version_id
            version.revision_reason = command.revision_reason
            version_repo.save(version)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Budget version could not be updated.") from exc

            from seeker_accounting.modules.audit.event_type_catalog import BUDGET_VERSION_UPDATED
            self._record_audit(version.company_id, BUDGET_VERSION_UPDATED, "ProjectBudgetVersion", version.id, "Updated budget version")
            return self._to_version_detail_dto(version)

    def get_version_detail(self, version_id: int) -> ProjectBudgetVersionDetailDTO:
        with self._unit_of_work_factory() as uow:
            version_repo = self._version_repository_factory(uow.session)
            version = version_repo.get_by_id(version_id)
            if version is None:
                raise NotFoundError(f"Budget version {version_id} not found.")
            return self._to_version_detail_dto(version)

    def list_versions(self, project_id: int) -> list[ProjectBudgetVersionListItemDTO]:
        with self._unit_of_work_factory() as uow:
            version_repo = self._version_repository_factory(uow.session)
            versions = version_repo.list_by_project(project_id)
            return [self._to_version_list_item_dto(v) for v in versions]

    # ── Line CRUD ────────────────────────────────────────────────────

    def add_line(self, command: AddProjectBudgetLineCommand) -> ProjectBudgetLineDTO:
        if command.line_number < 1:
            raise ValidationError("Line number must be at least 1.")
        if command.line_amount < 0:
            raise ValidationError("Line amount cannot be negative.")
        if command.quantity is not None and command.quantity < 0:
            raise ValidationError("Quantity cannot be negative.")
        if command.unit_rate is not None and command.unit_rate < 0:
            raise ValidationError("Unit rate cannot be negative.")
        if command.start_date and command.end_date and command.start_date > command.end_date:
            raise ValidationError("Start date cannot be after end date.")

        with self._unit_of_work_factory() as uow:
            version_repo = self._version_repository_factory(uow.session)
            version = version_repo.get_by_id(command.project_budget_version_id)
            if version is None:
                raise NotFoundError(f"Budget version {command.project_budget_version_id} not found.")
            if version.status_code not in _EDITABLE_STATUSES:
                raise ValidationError("Lines can only be added to draft or submitted budget versions.")

            line_repo = self._line_repository_factory(uow.session)
            existing_lines = line_repo.list_by_version(version.id)
            for el in existing_lines:
                if el.line_number == command.line_number:
                    raise ConflictError(
                        f"Line number {command.line_number} already exists in this version."
                    )

            self._validate_line_references(
                uow.session, version, command.project_job_id, command.project_cost_code_id
            )

            line = ProjectBudgetLine(
                project_budget_version_id=version.id,
                line_number=command.line_number,
                project_job_id=command.project_job_id,
                project_cost_code_id=command.project_cost_code_id,
                description=command.description,
                quantity=command.quantity,
                unit_rate=command.unit_rate,
                line_amount=command.line_amount,
                start_date=command.start_date,
                end_date=command.end_date,
                notes=command.notes,
            )
            line_repo.add(line)
            self._recalculate_total(version, existing_lines + [line])

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Budget line could not be created.") from exc

            return self._to_line_dto(line, uow.session)

    def update_line(
        self, line_id: int, command: UpdateProjectBudgetLineCommand
    ) -> ProjectBudgetLineDTO:
        if command.line_number < 1:
            raise ValidationError("Line number must be at least 1.")
        if command.line_amount < 0:
            raise ValidationError("Line amount cannot be negative.")
        if command.quantity is not None and command.quantity < 0:
            raise ValidationError("Quantity cannot be negative.")
        if command.unit_rate is not None and command.unit_rate < 0:
            raise ValidationError("Unit rate cannot be negative.")
        if command.start_date and command.end_date and command.start_date > command.end_date:
            raise ValidationError("Start date cannot be after end date.")

        with self._unit_of_work_factory() as uow:
            line_repo = self._line_repository_factory(uow.session)
            line = line_repo.get_by_id(line_id)
            if line is None:
                raise NotFoundError(f"Budget line {line_id} not found.")

            version_repo = self._version_repository_factory(uow.session)
            version = version_repo.get_by_id(line.project_budget_version_id)
            if version is None:
                raise NotFoundError("Budget version not found.")
            if version.status_code not in _EDITABLE_STATUSES:
                raise ValidationError("Lines can only be edited on draft or submitted budget versions.")

            if command.line_number != line.line_number:
                existing_lines = line_repo.list_by_version(version.id)
                for el in existing_lines:
                    if el.id != line_id and el.line_number == command.line_number:
                        raise ConflictError(
                            f"Line number {command.line_number} already exists in this version."
                        )

            self._validate_line_references(
                uow.session, version, command.project_job_id, command.project_cost_code_id
            )

            line.line_number = command.line_number
            line.project_job_id = command.project_job_id
            line.project_cost_code_id = command.project_cost_code_id
            line.description = command.description
            line.quantity = command.quantity
            line.unit_rate = command.unit_rate
            line.line_amount = command.line_amount
            line.start_date = command.start_date
            line.end_date = command.end_date
            line.notes = command.notes
            line_repo.save(line)

            all_lines = line_repo.list_by_version(version.id)
            self._recalculate_total(version, all_lines)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Budget line could not be updated.") from exc

            return self._to_line_dto(line, uow.session)

    def delete_line(self, line_id: int) -> None:
        with self._unit_of_work_factory() as uow:
            line_repo = self._line_repository_factory(uow.session)
            line = line_repo.get_by_id(line_id)
            if line is None:
                raise NotFoundError(f"Budget line {line_id} not found.")

            version_repo = self._version_repository_factory(uow.session)
            version = version_repo.get_by_id(line.project_budget_version_id)
            if version is None:
                raise NotFoundError("Budget version not found.")
            if version.status_code not in _EDITABLE_STATUSES:
                raise ValidationError("Lines can only be deleted from draft or submitted budget versions.")

            line_repo.delete(line)

            remaining = [l for l in line_repo.list_by_version(version.id) if l.id != line_id]
            self._recalculate_total(version, remaining)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Budget line could not be deleted.") from exc

    def list_lines(self, version_id: int) -> list[ProjectBudgetLineDTO]:
        with self._unit_of_work_factory() as uow:
            line_repo = self._line_repository_factory(uow.session)
            lines = line_repo.list_by_version(version_id)
            return [self._to_line_dto(l, uow.session) for l in lines]

    # ── Internal helpers ─────────────────────────────────────────────

    def _validate_line_references(
        self,
        session: Session,
        version: ProjectBudgetVersion,
        project_job_id: int | None,
        project_cost_code_id: int,
    ) -> None:
        if project_job_id is not None:
            job_repo = self._project_job_repository_factory(session)
            job = job_repo.get_by_id(project_job_id)
            if job is None:
                raise NotFoundError(f"Project job {project_job_id} not found.")
            if job.project_id != version.project_id:
                raise ValidationError("Job does not belong to the same project as this budget version.")

        cost_code_repo = self._project_cost_code_repository_factory(session)
        cost_code = cost_code_repo.get_by_id(project_cost_code_id)
        if cost_code is None:
            raise NotFoundError(f"Cost code {project_cost_code_id} not found.")
        if cost_code.company_id != version.company_id:
            raise ValidationError("Cost code does not belong to the same company.")

    def _recalculate_total(
        self, version: ProjectBudgetVersion, lines: list[ProjectBudgetLine]
    ) -> None:
        version.total_budget_amount = sum(
            (l.line_amount for l in lines), Decimal("0")
        )

    def _to_version_detail_dto(self, version: ProjectBudgetVersion) -> ProjectBudgetVersionDetailDTO:
        base_version_name: str | None = None
        if version.base_version is not None:
            base_version_name = version.base_version.version_name

        return ProjectBudgetVersionDetailDTO(
            id=version.id,
            company_id=version.company_id,
            project_id=version.project_id,
            version_number=version.version_number,
            version_name=version.version_name,
            version_type_code=version.version_type_code,
            status_code=version.status_code,
            base_version_id=version.base_version_id,
            base_version_name=base_version_name,
            budget_date=version.budget_date,
            revision_reason=version.revision_reason,
            total_budget_amount=version.total_budget_amount,
            approved_at=version.approved_at,
            approved_by_user_id=version.approved_by_user_id,
            created_at=version.created_at,
            updated_at=version.updated_at,
        )

    def _to_version_list_item_dto(self, version: ProjectBudgetVersion) -> ProjectBudgetVersionListItemDTO:
        return ProjectBudgetVersionListItemDTO(
            id=version.id,
            project_id=version.project_id,
            version_number=version.version_number,
            version_name=version.version_name,
            version_type_code=version.version_type_code,
            status_code=version.status_code,
            budget_date=version.budget_date,
            total_budget_amount=version.total_budget_amount,
            updated_at=version.updated_at,
        )

    def _to_line_dto(self, line: ProjectBudgetLine, session: Session) -> ProjectBudgetLineDTO:
        job_code: str | None = None
        if line.project_job_id is not None:
            job_repo = self._project_job_repository_factory(session)
            job = job_repo.get_by_id(line.project_job_id)
            job_code = job.job_code if job else None

        cost_code_name: str | None = None
        cost_code_repo = self._project_cost_code_repository_factory(session)
        cost_code = cost_code_repo.get_by_id(line.project_cost_code_id)
        cost_code_name = cost_code.name if cost_code else None

        return ProjectBudgetLineDTO(
            id=line.id,
            project_budget_version_id=line.project_budget_version_id,
            line_number=line.line_number,
            project_job_id=line.project_job_id,
            project_job_code=job_code,
            project_cost_code_id=line.project_cost_code_id,
            project_cost_code_name=cost_code_name,
            description=line.description,
            quantity=line.quantity,
            unit_rate=line.unit_rate,
            line_amount=line.line_amount,
            start_date=line.start_date,
            end_date=line.end_date,
            notes=line.notes,
            updated_at=line.updated_at,
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
        from seeker_accounting.modules.audit.event_type_catalog import MODULE_BUDGETING
        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type_code,
                    module_code=MODULE_BUDGETING,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    description=description,
                ),
            )
        except Exception:
            pass  # Audit must not break business operations
