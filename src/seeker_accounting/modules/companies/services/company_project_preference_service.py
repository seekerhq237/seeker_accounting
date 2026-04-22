from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.companies.dto.company_project_preference_dto import (
    CompanyProjectPreferenceDTO,
    UpdateCompanyProjectPreferencesCommand,
)
from seeker_accounting.modules.companies.models.company_project_preference import CompanyProjectPreference
from seeker_accounting.modules.companies.repositories.company_project_preference_repository import (
    CompanyProjectPreferenceRepository,
)
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

CompanyProjectPreferenceRepositoryFactory = Callable[[Session], CompanyProjectPreferenceRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]

_VALID_CONTROL_MODES = frozenset({"none", "warn", "hard_stop"})


class CompanyProjectPreferenceService:
    """Manage company-level project control preferences."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_project_preference_repository_factory: CompanyProjectPreferenceRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        audit_service: "AuditService | None" = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_project_preference_repository_factory = company_project_preference_repository_factory
        self._company_repository_factory = company_repository_factory
        self._audit_service = audit_service

    def get_company_project_preferences(self, company_id: int) -> CompanyProjectPreferenceDTO:
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            self.ensure_defaults(company_id)
            repository = self._company_project_preference_repository_factory(uow.session)
            preference = repository.get_by_company_id(company_id)
            if preference is None:
                raise NotFoundError(f"Company project preferences for company {company_id} not found.")
            return self._to_dto(preference)

    def update_company_project_preferences(
        self,
        company_id: int,
        command: UpdateCompanyProjectPreferencesCommand,
    ) -> CompanyProjectPreferenceDTO:
        self._validate_command(command)

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._company_project_preference_repository_factory(uow.session)

            preference = repository.get_by_company_id(company_id)
            if preference is None:
                preference = CompanyProjectPreference(
                    company_id=company_id,
                    allow_projects_without_contract=command.allow_projects_without_contract,
                    default_budget_control_mode_code=command.default_budget_control_mode_code,
                    default_commitment_control_mode_code=command.default_commitment_control_mode_code,
                    budget_warning_percent_threshold=command.budget_warning_percent_threshold,
                    require_job_on_cost_posting=command.require_job_on_cost_posting,
                    require_cost_code_on_cost_posting=command.require_cost_code_on_cost_posting,
                    updated_by_user_id=command.updated_by_user_id,
                )
                repository.add(preference)
            else:
                preference.allow_projects_without_contract = command.allow_projects_without_contract
                preference.default_budget_control_mode_code = command.default_budget_control_mode_code
                preference.default_commitment_control_mode_code = command.default_commitment_control_mode_code
                preference.budget_warning_percent_threshold = command.budget_warning_percent_threshold
                preference.require_job_on_cost_posting = command.require_job_on_cost_posting
                preference.require_cost_code_on_cost_posting = command.require_cost_code_on_cost_posting
                preference.updated_by_user_id = command.updated_by_user_id
                repository.save(preference)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Company project preferences could not be saved.") from exc

            from seeker_accounting.modules.audit.event_type_catalog import COMPANY_PROJECT_PREFERENCES_UPDATED
            self._record_audit(company_id, COMPANY_PROJECT_PREFERENCES_UPDATED, "CompanyProjectPreference", company_id, f"Updated project preferences for company id={company_id}")
            return self._to_dto(preference)

    def ensure_defaults(self, company_id: int) -> CompanyProjectPreferenceDTO:
        """Ensure default project preferences exist for a company."""
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._company_project_preference_repository_factory(uow.session)

            preference = repository.get_by_company_id(company_id)
            if preference is None:
                preference = CompanyProjectPreference(
                    company_id=company_id,
                    allow_projects_without_contract=True,
                    default_budget_control_mode_code="none",
                    default_commitment_control_mode_code="none",
                    budget_warning_percent_threshold=None,
                    require_job_on_cost_posting=False,
                    require_cost_code_on_cost_posting=False,
                    updated_by_user_id=None,
                )
                repository.add(preference)
                uow.commit()

            return self._to_dto(preference)

    def _validate_command(self, command: UpdateCompanyProjectPreferencesCommand) -> None:
        if command.default_budget_control_mode_code not in _VALID_CONTROL_MODES:
            raise ValidationError(
                f"Invalid budget control mode: {command.default_budget_control_mode_code}. "
                f"Valid: {', '.join(sorted(_VALID_CONTROL_MODES))}."
            )
        if command.default_commitment_control_mode_code not in _VALID_CONTROL_MODES:
            raise ValidationError(
                f"Invalid commitment control mode: {command.default_commitment_control_mode_code}. "
                f"Valid: {', '.join(sorted(_VALID_CONTROL_MODES))}."
            )
        if command.budget_warning_percent_threshold is not None and command.budget_warning_percent_threshold < 0:
            raise ValidationError("Budget warning percent threshold cannot be negative.")

    def _require_company_exists(self, session: Session, company_id: int) -> None:
        if self._company_repository_factory(session).get_by_id(company_id) is None:
            raise NotFoundError(f"Company {company_id} not found.")

    def _to_dto(self, preference: CompanyProjectPreference) -> CompanyProjectPreferenceDTO:
        return CompanyProjectPreferenceDTO(
            company_id=preference.company_id,
            allow_projects_without_contract=preference.allow_projects_without_contract,
            default_budget_control_mode_code=preference.default_budget_control_mode_code,
            default_commitment_control_mode_code=preference.default_commitment_control_mode_code,
            budget_warning_percent_threshold=float(preference.budget_warning_percent_threshold) if preference.budget_warning_percent_threshold is not None else None,
            require_job_on_cost_posting=preference.require_job_on_cost_posting,
            require_cost_code_on_cost_posting=preference.require_cost_code_on_cost_posting,
            updated_at=preference.updated_at,
            updated_by_user_id=preference.updated_by_user_id,
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
        from seeker_accounting.modules.audit.event_type_catalog import MODULE_COMPANIES
        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type_code,
                    module_code=MODULE_COMPANIES,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    description=description,
                ),
            )
        except Exception:
            pass  # Audit must not break business operations
