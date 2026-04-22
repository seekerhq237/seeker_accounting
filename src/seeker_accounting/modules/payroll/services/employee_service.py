from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.accounting.reference_data.repositories.currency_repository import (
    CurrencyRepository,
)
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.payroll.dto.employee_dto import (
    CreateEmployeeCommand,
    EmployeeDetailDTO,
    EmployeeListItemDTO,
    UpdateEmployeeCommand,
)
from seeker_accounting.modules.payroll.models.employee import Employee
from seeker_accounting.modules.payroll.repositories.department_repository import DepartmentRepository
from seeker_accounting.modules.payroll.repositories.employee_repository import EmployeeRepository
from seeker_accounting.modules.payroll.repositories.position_repository import PositionRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

EmployeeRepositoryFactory = Callable[[Session], EmployeeRepository]
DepartmentRepositoryFactory = Callable[[Session], DepartmentRepository]
PositionRepositoryFactory = Callable[[Session], PositionRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
CurrencyRepositoryFactory = Callable[[Session], CurrencyRepository]


class EmployeeService:
    """Manage employee records within a company's payroll."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        employee_repository_factory: EmployeeRepositoryFactory,
        department_repository_factory: DepartmentRepositoryFactory,
        position_repository_factory: PositionRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        currency_repository_factory: CurrencyRepositoryFactory,
        audit_service: "AuditService | None" = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._employee_repository_factory = employee_repository_factory
        self._department_repository_factory = department_repository_factory
        self._position_repository_factory = position_repository_factory
        self._company_repository_factory = company_repository_factory
        self._currency_repository_factory = currency_repository_factory
        self._audit_service = audit_service

    # ── Queries ───────────────────────────────────────────────────────────────

    def list_employees(
        self,
        company_id: int,
        active_only: bool = False,
        query: str | None = None,
        department_id: int | None = None,
        position_id: int | None = None,
    ) -> list[EmployeeListItemDTO]:
        with self._unit_of_work_factory() as uow:
            rows = self._employee_repository_factory(uow.session).list_by_company(
                company_id,
                active_only=active_only,
                query=query,
                department_id=department_id,
                position_id=position_id,
            )
            return [self._to_list_dto(r) for r in rows]

    def get_employee(self, company_id: int, employee_id: int) -> EmployeeDetailDTO:
        with self._unit_of_work_factory() as uow:
            row = self._employee_repository_factory(uow.session).get_by_id(company_id, employee_id)
            if row is None:
                raise NotFoundError(f"Employee {employee_id} not found.")
            return self._to_detail_dto(row)

    # ── Commands ──────────────────────────────────────────────────────────────

    def create_employee(
        self, company_id: int, command: CreateEmployeeCommand
    ) -> EmployeeDetailDTO:
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            self._validate_command_fields(uow.session, company_id, command.employee_number,
                                          command.display_name, command.first_name,
                                          command.last_name, command.base_currency_code,
                                          command.department_id, command.position_id,
                                          command.hire_date, command.termination_date)
            repo = self._employee_repository_factory(uow.session)
            if repo.get_by_number(company_id, command.employee_number.strip()) is not None:
                raise ConflictError(
                    f"Employee number '{command.employee_number}' already exists."
                )
            now = datetime.utcnow()
            emp = Employee(
                company_id=company_id,
                employee_number=command.employee_number.strip(),
                display_name=command.display_name.strip(),
                first_name=command.first_name.strip(),
                last_name=command.last_name.strip(),
                hire_date=command.hire_date,
                termination_date=command.termination_date,
                base_currency_code=command.base_currency_code.strip().upper(),
                department_id=command.department_id,
                position_id=command.position_id,
                phone=command.phone.strip() if command.phone else None,
                email=command.email.strip() if command.email else None,
                tax_identifier=command.tax_identifier.strip() if command.tax_identifier else None,
                cnps_number=command.cnps_number.strip() if command.cnps_number else None,
                default_payment_account_id=command.default_payment_account_id,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            repo.save(emp)
            uow.commit()
            # Reload with relationships
            row = self._employee_repository_factory(uow.session).get_by_id(company_id, emp.id)
            from seeker_accounting.modules.audit.event_type_catalog import EMPLOYEE_CREATED
            self._record_audit(company_id, EMPLOYEE_CREATED, "Employee", emp.id, f"Created employee '{command.employee_number}'")
            return self._to_detail_dto(row)  # type: ignore[arg-type]

    def update_employee(
        self, company_id: int, employee_id: int, command: UpdateEmployeeCommand
    ) -> EmployeeDetailDTO:
        with self._unit_of_work_factory() as uow:
            repo = self._employee_repository_factory(uow.session)
            emp = repo.get_by_id(company_id, employee_id)
            if emp is None:
                raise NotFoundError(f"Employee {employee_id} not found.")
            self._validate_command_fields(uow.session, company_id, command.employee_number,
                                          command.display_name, command.first_name,
                                          command.last_name, command.base_currency_code,
                                          command.department_id, command.position_id,
                                          command.hire_date, command.termination_date)
            existing = repo.get_by_number(company_id, command.employee_number.strip())
            if existing is not None and existing.id != employee_id:
                raise ConflictError(
                    f"Employee number '{command.employee_number}' already exists."
                )
            emp.employee_number = command.employee_number.strip()
            emp.display_name = command.display_name.strip()
            emp.first_name = command.first_name.strip()
            emp.last_name = command.last_name.strip()
            emp.hire_date = command.hire_date
            emp.termination_date = command.termination_date
            emp.base_currency_code = command.base_currency_code.strip().upper()
            emp.department_id = command.department_id
            emp.position_id = command.position_id
            emp.phone = command.phone.strip() if command.phone else None
            emp.email = command.email.strip() if command.email else None
            emp.tax_identifier = command.tax_identifier.strip() if command.tax_identifier else None
            emp.cnps_number = command.cnps_number.strip() if command.cnps_number else None
            emp.default_payment_account_id = command.default_payment_account_id
            emp.is_active = command.is_active
            emp.updated_at = datetime.utcnow()
            repo.save(emp)
            uow.commit()
            row = self._employee_repository_factory(uow.session).get_by_id(company_id, employee_id)
            from seeker_accounting.modules.audit.event_type_catalog import EMPLOYEE_UPDATED
            self._record_audit(company_id, EMPLOYEE_UPDATED, "Employee", emp.id, f"Updated employee id={employee_id}")
            return self._to_detail_dto(row)  # type: ignore[arg-type]

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _require_company(self, session: Session, company_id: int) -> None:
        if self._company_repository_factory(session).get_by_id(company_id) is None:
            raise NotFoundError(f"Company {company_id} not found.")

    def _validate_command_fields(
        self,
        session: Session,
        company_id: int,
        employee_number: str,
        display_name: str,
        first_name: str,
        last_name: str,
        base_currency_code: str,
        department_id: int | None,
        position_id: int | None,
        hire_date: object,
        termination_date: object,
    ) -> None:
        if not employee_number or not employee_number.strip():
            raise ValidationError("Employee number is required.")
        if not display_name or not display_name.strip():
            raise ValidationError("Display name is required.")
        if not first_name or not first_name.strip():
            raise ValidationError("First name is required.")
        if not last_name or not last_name.strip():
            raise ValidationError("Last name is required.")
        if not base_currency_code or not base_currency_code.strip():
            raise ValidationError("Base currency code is required.")
        if self._currency_repository_factory(session).get_by_code(
            base_currency_code.strip().upper()
        ) is None:
            raise ValidationError(f"Currency '{base_currency_code}' not found.")
        if hire_date is not None and termination_date is not None:
            if termination_date < hire_date:  # type: ignore[operator]
                raise ValidationError("Termination date cannot be before hire date.")
        if department_id is not None:
            dept = self._department_repository_factory(session).get_by_id(
                company_id, department_id
            )
            if dept is None:
                raise ValidationError(
                    f"Department {department_id} not found in this company."
                )
        if position_id is not None:
            pos = self._position_repository_factory(session).get_by_id(
                company_id, position_id
            )
            if pos is None:
                raise ValidationError(
                    f"Position {position_id} not found in this company."
                )

    def _to_list_dto(self, emp: Employee) -> EmployeeListItemDTO:
        return EmployeeListItemDTO(
            id=emp.id,
            company_id=emp.company_id,
            employee_number=emp.employee_number,
            display_name=emp.display_name,
            first_name=emp.first_name,
            last_name=emp.last_name,
            department_id=emp.department_id,
            department_name=emp.department.name if emp.department else None,
            position_id=emp.position_id,
            position_name=emp.position.name if emp.position else None,
            hire_date=emp.hire_date,
            termination_date=emp.termination_date,
            base_currency_code=emp.base_currency_code,
            is_active=emp.is_active,
        )

    def _to_detail_dto(self, emp: Employee) -> EmployeeDetailDTO:
        return EmployeeDetailDTO(
            id=emp.id,
            company_id=emp.company_id,
            employee_number=emp.employee_number,
            display_name=emp.display_name,
            first_name=emp.first_name,
            last_name=emp.last_name,
            department_id=emp.department_id,
            department_name=emp.department.name if emp.department else None,
            position_id=emp.position_id,
            position_name=emp.position.name if emp.position else None,
            hire_date=emp.hire_date,
            termination_date=emp.termination_date,
            phone=emp.phone,
            email=emp.email,
            tax_identifier=emp.tax_identifier,
            cnps_number=emp.cnps_number,
            default_payment_account_id=emp.default_payment_account_id,
            base_currency_code=emp.base_currency_code,
            is_active=emp.is_active,
            created_at=emp.created_at,
            updated_at=emp.updated_at,
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
