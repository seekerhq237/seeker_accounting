from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.payroll.dto.payroll_calculation_dto import (
    ComponentAssignmentListItemDTO,
    CreateComponentAssignmentCommand,
    UpdateComponentAssignmentCommand,
)
from seeker_accounting.modules.payroll.models.employee_component_assignment import (
    EmployeeComponentAssignment,
)
from seeker_accounting.modules.payroll.repositories.component_assignment_repository import (
    ComponentAssignmentRepository,
)
from seeker_accounting.modules.payroll.repositories.employee_repository import EmployeeRepository
from seeker_accounting.modules.payroll.repositories.payroll_component_repository import (
    PayrollComponentRepository,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

ComponentAssignmentRepositoryFactory = Callable[[Session], ComponentAssignmentRepository]
EmployeeRepositoryFactory = Callable[[Session], EmployeeRepository]
PayrollComponentRepositoryFactory = Callable[[Session], PayrollComponentRepository]


class ComponentAssignmentService:
    """Manage recurring payroll component assignments per employee."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        assignment_repository_factory: ComponentAssignmentRepositoryFactory,
        employee_repository_factory: EmployeeRepositoryFactory,
        component_repository_factory: PayrollComponentRepositoryFactory,
        audit_service: "AuditService | None" = None,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._assignment_repo_factory = assignment_repository_factory
        self._employee_repo_factory = employee_repository_factory
        self._component_repo_factory = component_repository_factory
        self._audit_service = audit_service

    def list_assignments(
        self,
        company_id: int,
        employee_id: int,
        active_only: bool = False,
    ) -> list[ComponentAssignmentListItemDTO]:
        with self._uow_factory() as uow:
            repo = self._assignment_repo_factory(uow.session)
            rows = repo.list_by_employee(company_id, employee_id, active_only=active_only)
            return [self._to_dto(r) for r in rows]

    def get_assignment(
        self, company_id: int, assignment_id: int
    ) -> ComponentAssignmentListItemDTO:
        with self._uow_factory() as uow:
            repo = self._assignment_repo_factory(uow.session)
            row = repo.get_by_id(company_id, assignment_id)
            if row is None:
                raise NotFoundError("Component assignment not found.")
            return self._to_dto(row)

    def create_assignment(
        self, company_id: int, cmd: CreateComponentAssignmentCommand
    ) -> ComponentAssignmentListItemDTO:
        self._validate_dates(cmd.effective_from, cmd.effective_to)
        with self._uow_factory() as uow:
            emp_repo = self._employee_repo_factory(uow.session)
            if emp_repo.get_by_id(company_id, cmd.employee_id) is None:
                raise NotFoundError("Employee not found.")

            comp_repo = self._component_repo_factory(uow.session)
            comp = comp_repo.get_by_id(company_id, cmd.component_id)
            if comp is None:
                raise NotFoundError("Payroll component not found.")

            repo = self._assignment_repo_factory(uow.session)
            if repo.check_duplicate(
                company_id, cmd.employee_id, cmd.component_id, cmd.effective_from
            ):
                raise ConflictError(
                    "An assignment for this component with this effective date already exists."
                )

            assignment = EmployeeComponentAssignment(
                company_id=company_id,
                employee_id=cmd.employee_id,
                component_id=cmd.component_id,
                override_amount=cmd.override_amount,
                override_rate=cmd.override_rate,
                effective_from=cmd.effective_from,
                effective_to=cmd.effective_to,
            )
            repo.save(assignment)
            uow.commit()
            uow.session.refresh(assignment)
            from seeker_accounting.modules.audit.event_type_catalog import COMPONENT_ASSIGNMENT_CREATED
            self._record_audit(company_id, COMPONENT_ASSIGNMENT_CREATED, "EmployeeComponentAssignment", assignment.id, f"Created component assignment for employee id={cmd.employee_id}")
            return self._to_dto(assignment)

    def update_assignment(
        self,
        company_id: int,
        assignment_id: int,
        cmd: UpdateComponentAssignmentCommand,
    ) -> ComponentAssignmentListItemDTO:
        self._validate_dates(cmd.effective_from, cmd.effective_to)
        with self._uow_factory() as uow:
            repo = self._assignment_repo_factory(uow.session)
            assignment = repo.get_by_id(company_id, assignment_id)
            if assignment is None:
                raise NotFoundError("Component assignment not found.")

            comp_repo = self._component_repo_factory(uow.session)
            comp = comp_repo.get_by_id(company_id, cmd.component_id)
            if comp is None:
                raise NotFoundError("Payroll component not found.")

            if repo.check_duplicate(
                company_id,
                assignment.employee_id,
                cmd.component_id,
                cmd.effective_from,
                exclude_id=assignment_id,
            ):
                raise ConflictError(
                    "Another assignment for this component with this effective date already exists."
                )

            assignment.component_id = cmd.component_id
            assignment.override_amount = cmd.override_amount
            assignment.override_rate = cmd.override_rate
            assignment.effective_from = cmd.effective_from
            assignment.effective_to = cmd.effective_to
            assignment.is_active = cmd.is_active

            uow.commit()
            uow.session.refresh(assignment)
            from seeker_accounting.modules.audit.event_type_catalog import COMPONENT_ASSIGNMENT_UPDATED
            self._record_audit(company_id, COMPONENT_ASSIGNMENT_UPDATED, "EmployeeComponentAssignment", assignment.id, f"Updated component assignment id={assignment_id}")
            return self._to_dto(assignment)

    def toggle_active(self, company_id: int, assignment_id: int) -> None:
        with self._uow_factory() as uow:
            repo = self._assignment_repo_factory(uow.session)
            assignment = repo.get_by_id(company_id, assignment_id)
            if assignment is None:
                raise NotFoundError("Component assignment not found.")
            assignment.is_active = not assignment.is_active
            uow.commit()
            from seeker_accounting.modules.audit.event_type_catalog import COMPONENT_ASSIGNMENT_UPDATED
            self._record_audit(company_id, COMPONENT_ASSIGNMENT_UPDATED, "EmployeeComponentAssignment", assignment_id, f"Toggled active status for assignment id={assignment_id}")

    @staticmethod
    def _validate_dates(effective_from, effective_to) -> None:
        if effective_to is not None and effective_to <= effective_from:
            raise ValidationError("Effective-to date must be after effective-from date.")

    @staticmethod
    def _to_dto(a: EmployeeComponentAssignment) -> ComponentAssignmentListItemDTO:
        from decimal import Decimal
        comp = a.component
        emp = a.employee
        return ComponentAssignmentListItemDTO(
            id=a.id,
            company_id=a.company_id,
            employee_id=a.employee_id,
            employee_display_name=emp.display_name if emp else "",
            component_id=a.component_id,
            component_code=comp.component_code if comp else "",
            component_name=comp.component_name if comp else "",
            component_type_code=comp.component_type_code if comp else "",
            calculation_method_code=comp.calculation_method_code if comp else "",
            override_amount=Decimal(str(a.override_amount)) if a.override_amount is not None else None,
            override_rate=Decimal(str(a.override_rate)) if a.override_rate is not None else None,
            effective_from=a.effective_from,
            effective_to=a.effective_to,
            is_active=a.is_active,
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
