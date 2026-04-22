from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.payroll.dto.payroll_calculation_dto import (
    CompensationProfileDetailDTO,
    CompensationProfileListItemDTO,
    CreateCompensationProfileCommand,
    UpdateCompensationProfileCommand,
)
from seeker_accounting.modules.payroll.models.employee_compensation_profile import (
    EmployeeCompensationProfile,
)
from seeker_accounting.modules.payroll.repositories.compensation_profile_repository import (
    CompensationProfileRepository,
)
from seeker_accounting.modules.payroll.repositories.employee_repository import EmployeeRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

CompensationProfileRepositoryFactory = Callable[[Session], CompensationProfileRepository]
EmployeeRepositoryFactory = Callable[[Session], EmployeeRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]


class CompensationProfileService:
    """Manage employee compensation profiles (salary and contract parameters)."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        profile_repository_factory: CompensationProfileRepositoryFactory,
        employee_repository_factory: EmployeeRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        audit_service: "AuditService | None" = None,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._profile_repo_factory = profile_repository_factory
        self._employee_repo_factory = employee_repository_factory
        self._company_repo_factory = company_repository_factory
        self._audit_service = audit_service

    # ── Queries ───────────────────────────────────────────────────────────────

    def list_profiles(
        self,
        company_id: int,
        employee_id: int | None = None,
        active_only: bool = False,
    ) -> list[CompensationProfileListItemDTO]:
        with self._uow_factory() as uow:
            repo = self._profile_repo_factory(uow.session)
            if employee_id is not None:
                profiles = repo.list_by_employee(company_id, employee_id, active_only=active_only)
            else:
                profiles = repo.list_by_company(company_id, active_only=active_only)
            return [self._to_list_dto(p) for p in profiles]

    def get_profile(self, company_id: int, profile_id: int) -> CompensationProfileDetailDTO:
        with self._uow_factory() as uow:
            repo = self._profile_repo_factory(uow.session)
            profile = repo.get_by_id(company_id, profile_id)
            if profile is None:
                raise NotFoundError("Compensation profile not found.")
            return self._to_detail_dto(profile)

    # ── Commands ──────────────────────────────────────────────────────────────

    def create_profile(
        self, company_id: int, cmd: CreateCompensationProfileCommand
    ) -> CompensationProfileDetailDTO:
        self._validate_profile_fields(cmd.basic_salary, cmd.effective_from, cmd.effective_to)
        with self._uow_factory() as uow:
            emp_repo = self._employee_repo_factory(uow.session)
            employee = emp_repo.get_by_id(company_id, cmd.employee_id)
            if employee is None:
                raise NotFoundError("Employee not found.")

            repo = self._profile_repo_factory(uow.session)
            if repo.check_duplicate(company_id, cmd.employee_id, cmd.effective_from):
                raise ConflictError(
                    "A compensation profile with this effective date already exists for this employee."
                )

            profile = EmployeeCompensationProfile(
                company_id=company_id,
                employee_id=cmd.employee_id,
                profile_name=cmd.profile_name.strip(),
                basic_salary=cmd.basic_salary,
                currency_code=cmd.currency_code,
                effective_from=cmd.effective_from,
                effective_to=cmd.effective_to,
                notes=cmd.notes,
            )
            repo.save(profile)
            uow.commit()
            uow.session.refresh(profile)
            from seeker_accounting.modules.audit.event_type_catalog import COMPENSATION_PROFILE_CREATED
            self._record_audit(company_id, COMPENSATION_PROFILE_CREATED, "EmployeeCompensationProfile", profile.id, f"Created compensation profile for employee id={cmd.employee_id}")
            return self._to_detail_dto(profile)

    def update_profile(
        self, company_id: int, profile_id: int, cmd: UpdateCompensationProfileCommand
    ) -> CompensationProfileDetailDTO:
        self._validate_profile_fields(cmd.basic_salary, cmd.effective_from, cmd.effective_to)
        with self._uow_factory() as uow:
            repo = self._profile_repo_factory(uow.session)
            profile = repo.get_by_id(company_id, profile_id)
            if profile is None:
                raise NotFoundError("Compensation profile not found.")
            if repo.check_duplicate(company_id, profile.employee_id, cmd.effective_from, exclude_id=profile_id):
                raise ConflictError(
                    "Another compensation profile with this effective date already exists for this employee."
                )

            profile.profile_name = cmd.profile_name.strip()
            profile.basic_salary = cmd.basic_salary
            profile.currency_code = cmd.currency_code
            profile.effective_from = cmd.effective_from
            profile.effective_to = cmd.effective_to
            profile.notes = cmd.notes
            profile.is_active = cmd.is_active

            uow.commit()
            uow.session.refresh(profile)
            from seeker_accounting.modules.audit.event_type_catalog import COMPENSATION_PROFILE_UPDATED
            self._record_audit(company_id, COMPENSATION_PROFILE_UPDATED, "EmployeeCompensationProfile", profile.id, f"Updated compensation profile id={profile_id}")
            return self._to_detail_dto(profile)

    def toggle_profile_active(self, company_id: int, profile_id: int) -> None:
        with self._uow_factory() as uow:
            repo = self._profile_repo_factory(uow.session)
            profile = repo.get_by_id(company_id, profile_id)
            if profile is None:
                raise NotFoundError("Compensation profile not found.")
            profile.is_active = not profile.is_active
            uow.commit()
            from seeker_accounting.modules.audit.event_type_catalog import COMPENSATION_PROFILE_UPDATED
            self._record_audit(company_id, COMPENSATION_PROFILE_UPDATED, "EmployeeCompensationProfile", profile_id, f"Toggled active status for profile id={profile_id}")

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _validate_profile_fields(basic_salary, effective_from: date, effective_to) -> None:
        from decimal import Decimal
        if Decimal(str(basic_salary)) <= 0:
            raise ValidationError("Basic salary must be greater than zero.")
        if effective_to is not None and effective_to <= effective_from:
            raise ValidationError("Effective-to date must be after effective-from date.")

    @staticmethod
    def _to_list_dto(p: EmployeeCompensationProfile) -> CompensationProfileListItemDTO:
        from decimal import Decimal
        return CompensationProfileListItemDTO(
            id=p.id,
            company_id=p.company_id,
            employee_id=p.employee_id,
            employee_number=p.employee.employee_number if p.employee else "",
            employee_display_name=p.employee.display_name if p.employee else "",
            profile_name=p.profile_name,
            basic_salary=Decimal(str(p.basic_salary)),
            currency_code=p.currency_code,
            effective_from=p.effective_from,
            effective_to=p.effective_to,
            is_active=p.is_active,
        )

    @staticmethod
    def _to_detail_dto(p: EmployeeCompensationProfile) -> CompensationProfileDetailDTO:
        from decimal import Decimal
        return CompensationProfileDetailDTO(
            id=p.id,
            company_id=p.company_id,
            employee_id=p.employee_id,
            employee_number=p.employee.employee_number if p.employee else "",
            employee_display_name=p.employee.display_name if p.employee else "",
            profile_name=p.profile_name,
            basic_salary=Decimal(str(p.basic_salary)),
            currency_code=p.currency_code,
            effective_from=p.effective_from,
            effective_to=p.effective_to,
            notes=p.notes,
            is_active=p.is_active,
            created_at=p.created_at,
            updated_at=p.updated_at,
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
        from seeker_accounting.modules.audit.event_type_catalog import MODULE_PAYROLL
        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type_code,
                    module_code=MODULE_PAYROLL,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    description=description,
                ),
            )
        except Exception:
            pass  # Audit must not break business operations
