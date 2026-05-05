from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.app.context.app_context import AppContext
from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.audit.dto.audit_event_dto import RecordAuditEventCommand
from seeker_accounting.modules.audit.services.audit_service import AuditService
from seeker_accounting.modules.payroll.dto.payroll_correction_dto import (
    ApplyPayrollCorrectionCommand,
    EmployeePayrollCorrectionDTO,
)
from seeker_accounting.modules.payroll.models.employee_payroll_correction import (
    EmployeePayrollCorrection,
)
from seeker_accounting.modules.payroll.payroll_permissions import PAYROLL_CORRECTION_MANAGE
from seeker_accounting.modules.payroll.repositories.employee_payroll_correction_repository import (
    EmployeePayrollCorrectionRepository,
)
from seeker_accounting.modules.payroll.repositories.employee_repository import EmployeeRepository
from seeker_accounting.modules.payroll.repositories.payroll_component_repository import (
    PayrollComponentRepository,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

CorrectionRepositoryFactory = Callable[[Session], EmployeePayrollCorrectionRepository]
EmployeeRepositoryFactory = Callable[[Session], EmployeeRepository]
ComponentRepositoryFactory = Callable[[Session], PayrollComponentRepository]


class PayrollCorrectionService:
    """Manage additive payroll correction facts."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        app_context: AppContext,
        correction_repository_factory: CorrectionRepositoryFactory,
        employee_repository_factory: EmployeeRepositoryFactory,
        component_repository_factory: ComponentRepositoryFactory,
        permission_service: PermissionService,
        audit_service: AuditService,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._app_context = app_context
        self._correction_repo_factory = correction_repository_factory
        self._employee_repo_factory = employee_repository_factory
        self._component_repo_factory = component_repository_factory
        self._permission_service = permission_service
        self._audit_service = audit_service

    def list_corrections(
        self, company_id: int, status_code: str | None = None
    ) -> list[EmployeePayrollCorrectionDTO]:
        self._permission_service.require_permission(PAYROLL_CORRECTION_MANAGE)
        with self._uow_factory() as uow:
            rows = self._correction_repo_factory(uow.session).list_by_company(
                company_id, status_code=status_code
            )
            return [self._to_dto(row) for row in rows]

    def apply_correction(
        self, company_id: int, cmd: ApplyPayrollCorrectionCommand
    ) -> EmployeePayrollCorrectionDTO:
        self._permission_service.require_permission(PAYROLL_CORRECTION_MANAGE)
        self._validate_period(cmd.period_year, cmd.period_month)
        amount = Decimal(str(cmd.correction_amount)).quantize(Decimal("0.0001"))
        if amount <= Decimal("0"):
            raise ValidationError("Correction amount must be greater than zero.")
        reason_code = (cmd.reason_code or "").strip().lower()
        if not reason_code:
            raise ValidationError("Correction reason code is required.")

        with self._uow_factory() as uow:
            employee = self._employee_repo_factory(uow.session).get_by_id(
                company_id, cmd.employee_id
            )
            if employee is None:
                raise NotFoundError("Employee not found.")
            if not employee.is_active:
                raise ValidationError("Corrections can only be queued for active employees.")
            component = self._component_repo_factory(uow.session).get_by_id(
                company_id, cmd.component_id
            )
            if component is None:
                raise NotFoundError("Payroll component not found.")
            if not component.is_active:
                raise ValidationError("Corrections can only use active payroll components.")

            correction = EmployeePayrollCorrection(
                company_id=company_id,
                employee_id=cmd.employee_id,
                component_id=cmd.component_id,
                period_year=cmd.period_year,
                period_month=cmd.period_month,
                correction_amount=amount,
                reason_code=reason_code,
                description=(cmd.description or "").strip() or None,
                source_run_id=cmd.source_run_id,
                status_code="pending",
                created_by_user_id=cmd.created_by_user_id or self._app_context.current_user_id,
            )
            self._correction_repo_factory(uow.session).save(correction)
            uow.session.flush()
            self._audit_service.record_event_in_session(
                uow.session,
                company_id,
                RecordAuditEventCommand(
                    event_type_code="PAYROLL_CORRECTION_CREATED",
                    module_code="payroll",
                    entity_type="employee_payroll_correction",
                    entity_id=correction.id,
                    description=(
                        f"Queued payroll correction for {employee.employee_number} "
                        f"on component {component.component_code}."
                    ),
                    detail_json=json.dumps(
                        {
                            "employee_id": cmd.employee_id,
                            "component_id": cmd.component_id,
                            "period_year": cmd.period_year,
                            "period_month": cmd.period_month,
                            "amount": str(amount),
                            "reason_code": reason_code,
                        }
                    ),
                ),
            )
            uow.commit()
            row = self._correction_repo_factory(uow.session).get_by_id(company_id, correction.id)
            return self._to_dto(row or correction)

    def void_correction(self, company_id: int, correction_id: int, reason: str) -> None:
        self._permission_service.require_permission(PAYROLL_CORRECTION_MANAGE)
        reason_text = (reason or "").strip()
        if not reason_text:
            raise ValidationError("A reason is required when voiding a correction.")
        with self._uow_factory() as uow:
            repo = self._correction_repo_factory(uow.session)
            correction = repo.get_by_id(company_id, correction_id)
            if correction is None:
                raise NotFoundError("Payroll correction not found.")
            if correction.status_code != "pending":
                raise ValidationError("Only pending corrections can be voided.")
            correction.status_code = "voided"
            correction.applied_at = datetime.now(timezone.utc)
            self._audit_service.record_event_in_session(
                uow.session,
                company_id,
                RecordAuditEventCommand(
                    event_type_code="PAYROLL_CORRECTION_VOIDED",
                    module_code="payroll",
                    entity_type="employee_payroll_correction",
                    entity_id=correction.id,
                    description=f"Voided payroll correction {correction.id}. Reason: {reason_text}",
                ),
            )
            uow.commit()

    @staticmethod
    def _validate_period(year: int, month: int) -> None:
        if not (2000 <= year <= 2100):
            raise ValidationError("Period year must be between 2000 and 2100.")
        if not (1 <= month <= 12):
            raise ValidationError("Period month must be between 1 and 12.")

    @staticmethod
    def _to_dto(row: EmployeePayrollCorrection) -> EmployeePayrollCorrectionDTO:
        employee = row.employee
        component = row.component
        return EmployeePayrollCorrectionDTO(
            id=row.id,
            company_id=row.company_id,
            employee_id=row.employee_id,
            employee_display_name=employee.display_name if employee else "",
            component_id=row.component_id,
            component_code=component.component_code if component else "",
            component_name=component.component_name if component else "",
            component_type_code=component.component_type_code if component else "",
            period_year=row.period_year,
            period_month=row.period_month,
            correction_amount=Decimal(str(row.correction_amount)),
            reason_code=row.reason_code,
            description=row.description,
            status_code=row.status_code,
            source_run_id=row.source_run_id,
            applied_run_id=row.applied_run_id,
            applied_run_employee_id=row.applied_run_employee_id,
            applied_at=row.applied_at,
            created_by_user_id=row.created_by_user_id,
            created_at=getattr(row, "created_at", None),
            updated_at=getattr(row, "updated_at", None),
        )
