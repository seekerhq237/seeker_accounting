from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.contracts_projects.dto.project_job_commands import (
    CreateProjectJobCommand,
    UpdateProjectJobCommand,
)
from seeker_accounting.modules.contracts_projects.dto.project_job_dto import (
    ProjectJobDetailDTO,
    ProjectJobListItemDTO,
)
from seeker_accounting.modules.contracts_projects.models.project_job import ProjectJob
from seeker_accounting.modules.contracts_projects.repositories.project_job_repository import ProjectJobRepository
from seeker_accounting.modules.contracts_projects.repositories.project_repository import ProjectRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

ProjectJobRepositoryFactory = Callable[[Session], ProjectJobRepository]
ProjectRepositoryFactory = Callable[[Session], ProjectRepository]

_VALID_JOB_STATUSES = frozenset({"active", "inactive", "closed"})


class ProjectStructureService:
    """Manage project jobs / work packages."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        project_job_repository_factory: ProjectJobRepositoryFactory,
        project_repository_factory: ProjectRepositoryFactory,
        audit_service: "AuditService | None" = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._project_job_repository_factory = project_job_repository_factory
        self._project_repository_factory = project_repository_factory
        self._audit_service = audit_service

    def create_job(self, command: CreateProjectJobCommand) -> ProjectJobDetailDTO:
        if not command.job_code or not command.job_code.strip():
            raise ValidationError("Job code is required.")
        if not command.job_name or not command.job_name.strip():
            raise ValidationError("Job name is required.")
        if command.start_date and command.planned_end_date and command.start_date > command.planned_end_date:
            raise ValidationError("Start date cannot be after planned end date.")

        with self._unit_of_work_factory() as uow:
            project_repo = self._project_repository_factory(uow.session)
            project = project_repo.get_by_id(command.project_id)
            if project is None:
                raise NotFoundError(f"Project {command.project_id} not found.")
            if project.company_id != command.company_id:
                raise ValidationError("Project does not belong to the specified company.")

            job_repo = self._project_job_repository_factory(uow.session)

            existing = job_repo.get_by_project_and_job_code(command.project_id, command.job_code.strip())
            if existing is not None:
                raise ConflictError(f"Job code '{command.job_code}' already exists in this project.")

            if command.parent_job_id is not None:
                parent = job_repo.get_by_id(command.parent_job_id)
                if parent is None:
                    raise NotFoundError(f"Parent job {command.parent_job_id} not found.")
                if parent.project_id != command.project_id:
                    raise ValidationError("Parent job does not belong to the same project.")

            job = ProjectJob(
                company_id=command.company_id,
                project_id=command.project_id,
                job_code=command.job_code.strip(),
                job_name=command.job_name.strip(),
                parent_job_id=command.parent_job_id,
                sequence_number=command.sequence_number,
                status_code="active",
                start_date=command.start_date,
                planned_end_date=command.planned_end_date,
                allow_direct_cost_posting=command.allow_direct_cost_posting,
                notes=command.notes,
            )
            job_repo.add(job)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Job could not be created.") from exc

            from seeker_accounting.modules.audit.event_type_catalog import PROJECT_JOB_CREATED
            self._record_audit(command.company_id, PROJECT_JOB_CREATED, "ProjectJob", job.id, f"Created job '{command.job_code}'")
            return self._to_detail_dto(job, uow.session)

    def update_job(self, job_id: int, command: UpdateProjectJobCommand) -> ProjectJobDetailDTO:
        if not command.job_name or not command.job_name.strip():
            raise ValidationError("Job name is required.")
        if command.start_date and command.planned_end_date and command.start_date > command.planned_end_date:
            raise ValidationError("Start date cannot be after planned end date.")

        with self._unit_of_work_factory() as uow:
            job_repo = self._project_job_repository_factory(uow.session)
            job = job_repo.get_by_id(job_id)
            if job is None:
                raise NotFoundError(f"Job {job_id} not found.")

            if command.parent_job_id is not None:
                if command.parent_job_id == job_id:
                    raise ValidationError("A job cannot be its own parent.")
                parent = job_repo.get_by_id(command.parent_job_id)
                if parent is None:
                    raise NotFoundError(f"Parent job {command.parent_job_id} not found.")
                if parent.project_id != job.project_id:
                    raise ValidationError("Parent job does not belong to the same project.")
                self._check_cycle(job_repo, job_id, command.parent_job_id)

            job.job_name = command.job_name.strip()
            job.parent_job_id = command.parent_job_id
            job.sequence_number = command.sequence_number
            job.start_date = command.start_date
            job.planned_end_date = command.planned_end_date
            job.allow_direct_cost_posting = command.allow_direct_cost_posting
            job.notes = command.notes
            job_repo.save(job)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Job could not be updated.") from exc

            from seeker_accounting.modules.audit.event_type_catalog import PROJECT_JOB_UPDATED
            self._record_audit(job.company_id, PROJECT_JOB_UPDATED, "ProjectJob", job.id, f"Updated job id={job_id}")
            return self._to_detail_dto(job, uow.session)

    def get_job_detail(self, job_id: int) -> ProjectJobDetailDTO:
        with self._unit_of_work_factory() as uow:
            job_repo = self._project_job_repository_factory(uow.session)
            job = job_repo.get_by_id(job_id)
            if job is None:
                raise NotFoundError(f"Job {job_id} not found.")
            return self._to_detail_dto(job, uow.session)

    def list_jobs(self, project_id: int) -> list[ProjectJobListItemDTO]:
        with self._unit_of_work_factory() as uow:
            job_repo = self._project_job_repository_factory(uow.session)
            jobs = job_repo.list_by_project(project_id)
            return [self._to_list_item_dto(j, uow.session) for j in jobs]

    def deactivate_job(self, job_id: int) -> ProjectJobDetailDTO:
        return self._change_status(job_id, "inactive", {"active"})

    def reactivate_job(self, job_id: int) -> ProjectJobDetailDTO:
        return self._change_status(job_id, "active", {"inactive"})

    def close_job(self, job_id: int) -> ProjectJobDetailDTO:
        return self._change_status(job_id, "closed", {"active", "inactive"})

    def _change_status(self, job_id: int, new_status: str, allowed_from: set[str]) -> ProjectJobDetailDTO:
        with self._unit_of_work_factory() as uow:
            job_repo = self._project_job_repository_factory(uow.session)
            job = job_repo.get_by_id(job_id)
            if job is None:
                raise NotFoundError(f"Job {job_id} not found.")
            if job.status_code not in allowed_from:
                raise ValidationError(
                    f"Cannot change job status from '{job.status_code}' to '{new_status}'."
                )
            job.status_code = new_status
            job_repo.save(job)
            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Job status could not be updated.") from exc
            from seeker_accounting.modules.audit.event_type_catalog import PROJECT_JOB_UPDATED
            self._record_audit(job.company_id, PROJECT_JOB_UPDATED, "ProjectJob", job.id, f"Changed job id={job_id} status to '{new_status}'")
            return self._to_detail_dto(job, uow.session)

    def _check_cycle(self, repo: ProjectJobRepository, job_id: int, proposed_parent_id: int) -> None:
        """Walk up from proposed_parent_id to ensure we don't create a cycle."""
        visited: set[int] = {job_id}
        current_id: int | None = proposed_parent_id
        while current_id is not None:
            if current_id in visited:
                raise ValidationError("Setting this parent would create a cycle in the job hierarchy.")
            visited.add(current_id)
            parent = repo.get_by_id(current_id)
            current_id = parent.parent_job_id if parent else None

    def _to_list_item_dto(self, job: ProjectJob, session: Session) -> ProjectJobListItemDTO:
        parent_job_code = None
        if job.parent_job_id is not None:
            parent = self._project_job_repository_factory(session).get_by_id(job.parent_job_id)
            parent_job_code = parent.job_code if parent else None

        return ProjectJobListItemDTO(
            id=job.id,
            project_id=job.project_id,
            job_code=job.job_code,
            job_name=job.job_name,
            parent_job_id=job.parent_job_id,
            parent_job_code=parent_job_code,
            sequence_number=job.sequence_number,
            status_code=job.status_code,
            start_date=job.start_date,
            planned_end_date=job.planned_end_date,
            allow_direct_cost_posting=job.allow_direct_cost_posting,
            updated_at=job.updated_at,
        )

    def _to_detail_dto(self, job: ProjectJob, session: Session) -> ProjectJobDetailDTO:
        parent_job_code = None
        if job.parent_job_id is not None:
            parent = self._project_job_repository_factory(session).get_by_id(job.parent_job_id)
            parent_job_code = parent.job_code if parent else None

        return ProjectJobDetailDTO(
            id=job.id,
            company_id=job.company_id,
            project_id=job.project_id,
            job_code=job.job_code,
            job_name=job.job_name,
            parent_job_id=job.parent_job_id,
            parent_job_code=parent_job_code,
            sequence_number=job.sequence_number,
            status_code=job.status_code,
            start_date=job.start_date,
            planned_end_date=job.planned_end_date,
            actual_end_date=job.actual_end_date,
            allow_direct_cost_posting=job.allow_direct_cost_posting,
            notes=job.notes,
            created_at=job.created_at,
            updated_at=job.updated_at,
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
