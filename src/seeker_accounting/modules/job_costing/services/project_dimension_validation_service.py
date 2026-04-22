from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.modules.contracts_projects.repositories.contract_repository import ContractRepository
from seeker_accounting.modules.contracts_projects.repositories.project_cost_code_repository import ProjectCostCodeRepository
from seeker_accounting.modules.contracts_projects.repositories.project_job_repository import ProjectJobRepository
from seeker_accounting.modules.contracts_projects.repositories.project_repository import ProjectRepository
from seeker_accounting.platform.exceptions import ValidationError

ContractRepositoryFactory = Callable[[Session], ContractRepository]
ProjectRepositoryFactory = Callable[[Session], ProjectRepository]
ProjectJobRepositoryFactory = Callable[[Session], ProjectJobRepository]
ProjectCostCodeRepositoryFactory = Callable[[Session], ProjectCostCodeRepository]


@dataclass(frozen=True, slots=True)
class ResolvedDimensions:
    contract_id: int | None
    project_id: int | None
    project_job_id: int | None
    project_cost_code_id: int | None


class ProjectDimensionValidationService:
    def __init__(
        self,
        contract_repository_factory: ContractRepositoryFactory,
        project_repository_factory: ProjectRepositoryFactory,
        project_job_repository_factory: ProjectJobRepositoryFactory,
        project_cost_code_repository_factory: ProjectCostCodeRepositoryFactory,
    ) -> None:
        self._contract_repository_factory = contract_repository_factory
        self._project_repository_factory = project_repository_factory
        self._project_job_repository_factory = project_job_repository_factory
        self._project_cost_code_repository_factory = project_cost_code_repository_factory

    def validate_header_dimensions(
        self,
        session: Session,
        company_id: int,
        contract_id: int | None,
        project_id: int | None,
    ) -> None:
        if contract_id is not None:
            self._validate_contract_company(session, company_id, contract_id)
        if project_id is not None:
            self._validate_project_company(session, company_id, project_id)
        if contract_id is not None and project_id is not None:
            self._validate_contract_project_compatibility(session, contract_id, project_id)

    def validate_line_dimensions(
        self,
        session: Session,
        company_id: int,
        contract_id: int | None,
        project_id: int | None,
        project_job_id: int | None,
        project_cost_code_id: int | None,
        line_number: int,
    ) -> None:
        if contract_id is not None:
            self._validate_contract_company(session, company_id, contract_id, line_number)
        if project_id is not None:
            self._validate_project_company(session, company_id, project_id, line_number)
        if contract_id is not None and project_id is not None:
            self._validate_contract_project_compatibility(session, contract_id, project_id, line_number)
        if project_job_id is not None:
            self._validate_job_project(session, project_id, project_job_id, line_number)
        if project_cost_code_id is not None:
            self._validate_cost_code_company(session, company_id, project_cost_code_id, line_number)

    def resolve_line_dimensions(
        self,
        header_contract_id: int | None,
        header_project_id: int | None,
        line_contract_id: int | None,
        line_project_id: int | None,
        line_project_job_id: int | None,
        line_project_cost_code_id: int | None,
    ) -> ResolvedDimensions:
        resolved_contract_id = line_contract_id if line_contract_id is not None else header_contract_id
        resolved_project_id = line_project_id if line_project_id is not None else header_project_id
        return ResolvedDimensions(
            contract_id=resolved_contract_id,
            project_id=resolved_project_id,
            project_job_id=line_project_job_id,
            project_cost_code_id=line_project_cost_code_id,
        )

    # ------------------------------------------------------------------
    # Internal validators
    # ------------------------------------------------------------------

    def _validate_contract_company(
        self, session: Session, company_id: int, contract_id: int, line_number: int | None = None
    ) -> None:
        repo = self._contract_repository_factory(session)
        contract = repo.get_by_company_and_id(company_id, contract_id)
        if contract is None:
            prefix = f"Line {line_number}: " if line_number is not None else ""
            raise ValidationError(f"{prefix}Contract does not belong to the active company.")

    def _validate_project_company(
        self, session: Session, company_id: int, project_id: int, line_number: int | None = None
    ) -> None:
        repo = self._project_repository_factory(session)
        project = repo.get_by_company_and_id(company_id, project_id)
        if project is None:
            prefix = f"Line {line_number}: " if line_number is not None else ""
            raise ValidationError(f"{prefix}Project does not belong to the active company.")

    def _validate_contract_project_compatibility(
        self, session: Session, contract_id: int, project_id: int, line_number: int | None = None
    ) -> None:
        repo = self._project_repository_factory(session)
        project = repo.get_by_id(project_id)
        if project is None:
            prefix = f"Line {line_number}: " if line_number is not None else ""
            raise ValidationError(f"{prefix}Project not found.")
        if project.contract_id is not None and project.contract_id != contract_id:
            prefix = f"Line {line_number}: " if line_number is not None else ""
            raise ValidationError(
                f"{prefix}Project is linked to a different contract."
            )

    def _validate_job_project(
        self, session: Session, project_id: int | None, project_job_id: int, line_number: int
    ) -> None:
        if project_id is None:
            raise ValidationError(f"Line {line_number}: Project job requires a project to be set.")
        repo = self._project_job_repository_factory(session)
        job = repo.get_by_id(project_job_id)
        if job is None:
            raise ValidationError(f"Line {line_number}: Project job not found.")
        project = self._project_repository_factory(session).get_by_id(project_id)
        if project is None or job.company_id != project.company_id:
            raise ValidationError(f"Line {line_number}: Project job does not belong to the active company.")
        if job.project_id != project_id:
            raise ValidationError(f"Line {line_number}: Project job does not belong to the selected project.")

    def _validate_cost_code_company(
        self, session: Session, company_id: int, cost_code_id: int, line_number: int
    ) -> None:
        repo = self._project_cost_code_repository_factory(session)
        cost_code = repo.get_by_id(cost_code_id)
        if cost_code is None:
            raise ValidationError(f"Line {line_number}: Project cost code not found.")
        if cost_code.company_id != company_id:
            raise ValidationError(f"Line {line_number}: Project cost code does not belong to the active company.")
