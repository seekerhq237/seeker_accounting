from __future__ import annotations

import json
from datetime import datetime
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.audit.dto.audit_event_dto import RecordAuditEventCommand
from seeker_accounting.modules.audit.services.audit_service import AuditService
from seeker_accounting.modules.accounting.reference_data.repositories.currency_repository import (
    CurrencyRepository,
)
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.payroll.payroll_permissions import PAYROLL_SETUP_MANAGE
from seeker_accounting.modules.payroll.dto.payroll_setup_commands import (
    CompanyPayrollSettingsDTO,
    CreateDepartmentCommand,
    CreatePositionCommand,
    DepartmentDTO,
    PositionDTO,
    UpdateDepartmentCommand,
    UpdatePositionCommand,
    UpsertCompanyPayrollSettingsCommand,
)
from seeker_accounting.modules.payroll.dto.payroll_setup_dto import PayrollSetupWorkspaceDTO
from seeker_accounting.modules.payroll.models.company_payroll_setting import CompanyPayrollSetting
from seeker_accounting.modules.payroll.models.department import Department
from seeker_accounting.modules.payroll.models.position import Position
from seeker_accounting.modules.payroll.repositories.company_payroll_setting_repository import (
    CompanyPayrollSettingRepository,
)
from seeker_accounting.modules.payroll.repositories.department_repository import DepartmentRepository
from seeker_accounting.modules.payroll.repositories.position_repository import PositionRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

CompanyPayrollSettingRepositoryFactory = Callable[[Session], CompanyPayrollSettingRepository]
DepartmentRepositoryFactory = Callable[[Session], DepartmentRepository]
PositionRepositoryFactory = Callable[[Session], PositionRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
CurrencyRepositoryFactory = Callable[[Session], CurrencyRepository]

_VALID_PAY_FREQUENCIES = frozenset({
    "monthly", "bi_monthly", "bi_weekly", "weekly", "daily",
})


class PayrollSetupService:
    """Manage company payroll settings, departments, and positions."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        settings_repository_factory: CompanyPayrollSettingRepositoryFactory,
        department_repository_factory: DepartmentRepositoryFactory,
        position_repository_factory: PositionRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        currency_repository_factory: CurrencyRepositoryFactory,
        permission_service: PermissionService,
        audit_service: AuditService,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._settings_repository_factory = settings_repository_factory
        self._department_repository_factory = department_repository_factory
        self._position_repository_factory = position_repository_factory
        self._company_repository_factory = company_repository_factory
        self._currency_repository_factory = currency_repository_factory
        self._permission_service = permission_service
        self._audit_service = audit_service

    # ── Company Payroll Settings ──────────────────────────────────────────────

    def get_company_payroll_settings(self, company_id: int) -> CompanyPayrollSettingsDTO | None:
        self._permission_service.require_permission(PAYROLL_SETUP_MANAGE)
        with self._unit_of_work_factory() as uow:
            row = self._settings_repository_factory(uow.session).get_by_company(company_id)
            return self._settings_to_dto(row) if row else None

    def upsert_company_payroll_settings(
        self, company_id: int, command: UpsertCompanyPayrollSettingsCommand
    ) -> CompanyPayrollSettingsDTO:
        self._permission_service.require_permission(PAYROLL_SETUP_MANAGE)
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            self._validate_settings_command(uow.session, command)

            repo = self._settings_repository_factory(uow.session)
            row = repo.get_by_company(company_id)
            now = datetime.utcnow()

            if row is None:
                row = CompanyPayrollSetting(
                    company_id=company_id,
                    updated_at=now,
                )

            row.statutory_pack_version_code = command.statutory_pack_version_code
            row.cnps_regime_code = command.cnps_regime_code
            row.accident_risk_class_code = command.accident_risk_class_code
            row.default_pay_frequency_code = command.default_pay_frequency_code
            row.default_payroll_currency_code = command.default_payroll_currency_code
            row.overtime_policy_mode_code = command.overtime_policy_mode_code
            row.benefit_in_kind_policy_mode_code = command.benefit_in_kind_policy_mode_code
            row.payroll_number_prefix = command.payroll_number_prefix
            row.payroll_number_padding_width = command.payroll_number_padding_width
            row.updated_at = now
            row.updated_by_user_id = command.updated_by_user_id

            repo.save(row)
            self._audit_service.record_event_in_session(
                uow.session,
                company_id,
                RecordAuditEventCommand(
                    event_type_code="PAYROLL_SETTINGS_UPDATED",
                    module_code="payroll",
                    entity_type="company_payroll_setting",
                    entity_id=row.company_id,
                    description="Updated company payroll settings.",
                    detail_json=json.dumps({
                        "default_pay_frequency_code": command.default_pay_frequency_code,
                        "default_payroll_currency_code": command.default_payroll_currency_code,
                        "statutory_pack_version_code": command.statutory_pack_version_code,
                    }),
                ),
            )
            uow.commit()
            return self._settings_to_dto(row)

    def get_payroll_setup_workspace(self, company_id: int) -> PayrollSetupWorkspaceDTO:
        self._permission_service.require_permission(PAYROLL_SETUP_MANAGE)
        with self._unit_of_work_factory() as uow:
            settings = self._settings_repository_factory(uow.session).get_by_company(company_id)
            dept_count = len(
                self._department_repository_factory(uow.session).list_by_company(company_id)
            )
            pos_count = len(
                self._position_repository_factory(uow.session).list_by_company(company_id)
            )
            return PayrollSetupWorkspaceDTO(
                company_id=company_id,
                settings=self._settings_to_dto(settings) if settings else None,
                department_count=dept_count,
                position_count=pos_count,
            )

    # ── Departments ───────────────────────────────────────────────────────────

    def list_departments(
        self, company_id: int, active_only: bool = False
    ) -> list[DepartmentDTO]:
        self._permission_service.require_permission(PAYROLL_SETUP_MANAGE)
        with self._unit_of_work_factory() as uow:
            rows = self._department_repository_factory(uow.session).list_by_company(
                company_id, active_only=active_only
            )
            return [self._dept_to_dto(r) for r in rows]

    def get_department(self, company_id: int, department_id: int) -> DepartmentDTO:
        self._permission_service.require_permission(PAYROLL_SETUP_MANAGE)
        with self._unit_of_work_factory() as uow:
            row = self._department_repository_factory(uow.session).get_by_id(
                company_id, department_id
            )
            if row is None:
                raise NotFoundError(f"Department {department_id} not found.")
            return self._dept_to_dto(row)

    def create_department(
        self, company_id: int, command: CreateDepartmentCommand
    ) -> DepartmentDTO:
        self._permission_service.require_permission(PAYROLL_SETUP_MANAGE)
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            self._validate_dept_fields(command.code, command.name)
            repo = self._department_repository_factory(uow.session)
            if repo.get_by_code(company_id, command.code.strip().upper()) is not None:
                raise ConflictError(f"Department code '{command.code}' already exists.")
            dept = Department(
                company_id=company_id,
                code=command.code.strip().upper(),
                name=command.name.strip(),
                is_active=True,
            )
            repo.save(dept)
            uow.session.flush()
            self._audit_service.record_event_in_session(
                uow.session,
                company_id,
                RecordAuditEventCommand(
                    event_type_code="PAYROLL_DEPARTMENT_CREATED",
                    module_code="payroll",
                    entity_type="department",
                    entity_id=dept.id,
                    description=f"Created department '{dept.code}'.",
                ),
            )
            uow.commit()
            return self._dept_to_dto(dept)

    def update_department(
        self, company_id: int, department_id: int, command: UpdateDepartmentCommand
    ) -> DepartmentDTO:
        self._permission_service.require_permission(PAYROLL_SETUP_MANAGE)
        with self._unit_of_work_factory() as uow:
            repo = self._department_repository_factory(uow.session)
            dept = repo.get_by_id(company_id, department_id)
            if dept is None:
                raise NotFoundError(f"Department {department_id} not found.")
            self._validate_dept_fields(command.code, command.name)
            existing = repo.get_by_code(company_id, command.code.strip().upper())
            if existing is not None and existing.id != department_id:
                raise ConflictError(f"Department code '{command.code}' already exists.")
            dept.code = command.code.strip().upper()
            dept.name = command.name.strip()
            dept.is_active = command.is_active
            repo.save(dept)
            self._audit_service.record_event_in_session(
                uow.session,
                company_id,
                RecordAuditEventCommand(
                    event_type_code="PAYROLL_DEPARTMENT_UPDATED",
                    module_code="payroll",
                    entity_type="department",
                    entity_id=dept.id,
                    description=f"Updated department '{dept.code}'.",
                ),
            )
            uow.commit()
            return self._dept_to_dto(dept)

    # ── Positions ─────────────────────────────────────────────────────────────

    def list_positions(
        self, company_id: int, active_only: bool = False
    ) -> list[PositionDTO]:
        self._permission_service.require_permission(PAYROLL_SETUP_MANAGE)
        with self._unit_of_work_factory() as uow:
            rows = self._position_repository_factory(uow.session).list_by_company(
                company_id, active_only=active_only
            )
            return [self._pos_to_dto(r) for r in rows]

    def get_position(self, company_id: int, position_id: int) -> PositionDTO:
        self._permission_service.require_permission(PAYROLL_SETUP_MANAGE)
        with self._unit_of_work_factory() as uow:
            row = self._position_repository_factory(uow.session).get_by_id(
                company_id, position_id
            )
            if row is None:
                raise NotFoundError(f"Position {position_id} not found.")
            return self._pos_to_dto(row)

    def create_position(
        self, company_id: int, command: CreatePositionCommand
    ) -> PositionDTO:
        self._permission_service.require_permission(PAYROLL_SETUP_MANAGE)
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            self._validate_pos_fields(command.code, command.name)
            repo = self._position_repository_factory(uow.session)
            if repo.get_by_code(company_id, command.code.strip().upper()) is not None:
                raise ConflictError(f"Position code '{command.code}' already exists.")
            pos = Position(
                company_id=company_id,
                code=command.code.strip().upper(),
                name=command.name.strip(),
                is_active=True,
            )
            repo.save(pos)
            uow.session.flush()
            self._audit_service.record_event_in_session(
                uow.session,
                company_id,
                RecordAuditEventCommand(
                    event_type_code="PAYROLL_POSITION_CREATED",
                    module_code="payroll",
                    entity_type="position",
                    entity_id=pos.id,
                    description=f"Created position '{pos.code}'.",
                ),
            )
            uow.commit()
            return self._pos_to_dto(pos)

    def update_position(
        self, company_id: int, position_id: int, command: UpdatePositionCommand
    ) -> PositionDTO:
        self._permission_service.require_permission(PAYROLL_SETUP_MANAGE)
        with self._unit_of_work_factory() as uow:
            repo = self._position_repository_factory(uow.session)
            pos = repo.get_by_id(company_id, position_id)
            if pos is None:
                raise NotFoundError(f"Position {position_id} not found.")
            self._validate_pos_fields(command.code, command.name)
            existing = repo.get_by_code(company_id, command.code.strip().upper())
            if existing is not None and existing.id != position_id:
                raise ConflictError(f"Position code '{command.code}' already exists.")
            pos.code = command.code.strip().upper()
            pos.name = command.name.strip()
            pos.is_active = command.is_active
            repo.save(pos)
            self._audit_service.record_event_in_session(
                uow.session,
                company_id,
                RecordAuditEventCommand(
                    event_type_code="PAYROLL_POSITION_UPDATED",
                    module_code="payroll",
                    entity_type="position",
                    entity_id=pos.id,
                    description=f"Updated position '{pos.code}'.",
                ),
            )
            uow.commit()
            return self._pos_to_dto(pos)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _require_company(self, session: Session, company_id: int) -> None:
        if self._company_repository_factory(session).get_by_id(company_id) is None:
            raise NotFoundError(f"Company {company_id} not found.")

    def _validate_settings_command(
        self, session: Session, cmd: UpsertCompanyPayrollSettingsCommand
    ) -> None:
        if not cmd.default_pay_frequency_code or not cmd.default_pay_frequency_code.strip():
            raise ValidationError("Default pay frequency code is required.")
        if cmd.default_pay_frequency_code not in _VALID_PAY_FREQUENCIES:
            raise ValidationError(
                f"Pay frequency '{cmd.default_pay_frequency_code}' is not valid. "
                f"Valid: {', '.join(sorted(_VALID_PAY_FREQUENCIES))}."
            )
        if not cmd.default_payroll_currency_code or not cmd.default_payroll_currency_code.strip():
            raise ValidationError("Default payroll currency code is required.")
        currency_repo = self._currency_repository_factory(session)
        if currency_repo.get_by_code(cmd.default_payroll_currency_code) is None:
            raise ValidationError(
                f"Currency '{cmd.default_payroll_currency_code}' not found."
            )
        if cmd.payroll_number_padding_width is not None and cmd.payroll_number_padding_width < 1:
            raise ValidationError("Payroll number padding width must be at least 1.")

    def _validate_dept_fields(self, code: str, name: str) -> None:
        if not code or not code.strip():
            raise ValidationError("Department code is required.")
        if not name or not name.strip():
            raise ValidationError("Department name is required.")

    def _validate_pos_fields(self, code: str, name: str) -> None:
        if not code or not code.strip():
            raise ValidationError("Position code is required.")
        if not name or not name.strip():
            raise ValidationError("Position name is required.")

    def _settings_to_dto(self, row: CompanyPayrollSetting) -> CompanyPayrollSettingsDTO:
        return CompanyPayrollSettingsDTO(
            company_id=row.company_id,
            statutory_pack_version_code=row.statutory_pack_version_code,
            cnps_regime_code=row.cnps_regime_code,
            accident_risk_class_code=row.accident_risk_class_code,
            default_pay_frequency_code=row.default_pay_frequency_code,
            default_payroll_currency_code=row.default_payroll_currency_code,
            overtime_policy_mode_code=row.overtime_policy_mode_code,
            benefit_in_kind_policy_mode_code=row.benefit_in_kind_policy_mode_code,
            payroll_number_prefix=row.payroll_number_prefix,
            payroll_number_padding_width=row.payroll_number_padding_width,
            updated_at=row.updated_at,
            updated_by_user_id=row.updated_by_user_id,
        )

    def _dept_to_dto(self, dept: Department) -> DepartmentDTO:
        return DepartmentDTO(
            id=dept.id,
            company_id=dept.company_id,
            code=dept.code,
            name=dept.name,
            is_active=dept.is_active,
            created_at=dept.created_at,
            updated_at=dept.updated_at,
        )

    def _pos_to_dto(self, pos: Position) -> PositionDTO:
        return PositionDTO(
            id=pos.id,
            company_id=pos.company_id,
            code=pos.code,
            name=pos.name,
            is_active=pos.is_active,
            created_at=pos.created_at,
            updated_at=pos.updated_at,
        )
