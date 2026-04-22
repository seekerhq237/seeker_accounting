from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.job_costing.services.project_dimension_validation_service import (
    ProjectDimensionValidationService,
)
from seeker_accounting.modules.payroll.dto.payroll_project_allocation_commands import (
    PayrollProjectAllocationLineCommand,
    ReplacePayrollProjectAllocationsCommand,
)
from seeker_accounting.modules.payroll.dto.payroll_project_allocation_dto import (
    PayrollProjectAllocationLineDTO,
    PayrollProjectAllocationSetDTO,
)
from seeker_accounting.modules.payroll.models.payroll_run import PayrollRun
from seeker_accounting.modules.payroll.models.payroll_run_employee import PayrollRunEmployee
from seeker_accounting.modules.payroll.models.payroll_run_employee_project_allocation import (
    PayrollRunEmployeeProjectAllocation,
)
from seeker_accounting.modules.payroll.repositories.payroll_run_employee_project_allocation_repository import (
    PayrollRunEmployeeProjectAllocationRepository,
)
from seeker_accounting.modules.payroll.repositories.payroll_run_repository import (
    PayrollRunEmployeeRepository,
    PayrollRunRepository,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

PayrollRunRepositoryFactory = Callable[[Session], PayrollRunRepository]
PayrollRunEmployeeRepositoryFactory = Callable[[Session], PayrollRunEmployeeRepository]
PayrollRunEmployeeProjectAllocationRepositoryFactory = Callable[
    [Session], PayrollRunEmployeeProjectAllocationRepository
]

_ALLOCATION_BASIS_CODES = frozenset({"percent", "amount", "hours"})
_EDITABLE_RUN_STATUSES = frozenset({"draft", "calculated"})
_MONEY_SCALE = Decimal("0.0001")
_HUNDRED_PERCENT = Decimal("100.0000")


class PayrollProjectAllocationService:
    """Manage project allocations for payroll run employees.

    Slice 15.6 allocates payroll labour cost against the preserved payroll field
    `employer_cost_base`, which is the existing total employer cost for the run
    employee. This keeps payroll calculation truth unchanged while creating a
    separate management-cost bridge for project costing.
    """

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        run_repository_factory: PayrollRunRepositoryFactory,
        run_employee_repository_factory: PayrollRunEmployeeRepositoryFactory,
        allocation_repository_factory: PayrollRunEmployeeProjectAllocationRepositoryFactory,
        project_dimension_validation_service: ProjectDimensionValidationService,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._run_repository_factory = run_repository_factory
        self._run_employee_repository_factory = run_employee_repository_factory
        self._allocation_repository_factory = allocation_repository_factory
        self._project_dimension_validation_service = project_dimension_validation_service

    def list_allocations(
        self,
        company_id: int,
        payroll_run_employee_id: int,
    ) -> tuple[PayrollProjectAllocationLineDTO, ...]:
        return self.get_allocation_set(company_id, payroll_run_employee_id).lines

    def get_allocation_set(
        self,
        company_id: int,
        payroll_run_employee_id: int,
    ) -> PayrollProjectAllocationSetDTO:
        with self._unit_of_work_factory() as uow:
            run_employee, run = self._require_run_employee_context(
                session=uow.session,
                company_id=company_id,
                payroll_run_employee_id=payroll_run_employee_id,
            )
            allocation_repo = self._allocation_repository_factory(uow.session)
            allocations = allocation_repo.list_by_payroll_run_employee(payroll_run_employee_id)
            return self._build_allocation_set_dto(run_employee, run, allocations)

    def replace_allocations(
        self,
        company_id: int,
        payroll_run_employee_id: int,
        command: ReplacePayrollProjectAllocationsCommand,
    ) -> PayrollProjectAllocationSetDTO:
        normalized_lines = self._normalize_command_lines(command.lines)

        with self._unit_of_work_factory() as uow:
            run_employee, run = self._require_run_employee_context(
                session=uow.session,
                company_id=company_id,
                payroll_run_employee_id=payroll_run_employee_id,
            )
            self._assert_editable(run_employee, run)

            allocation_repo = self._allocation_repository_factory(uow.session)
            base_amount = self._get_allocation_base_amount(run_employee)

            if not normalized_lines:
                if base_amount != Decimal("0.0000"):
                    raise ValidationError(
                        "Project allocations must fully reconcile to employer cost before they can be saved."
                    )
                allocation_repo.delete_all_for_payroll_run_employee(payroll_run_employee_id)
                uow.commit()
                return self._build_allocation_set_dto(run_employee, run, [])

            self._validate_dimensions(
                session=uow.session,
                company_id=company_id,
                lines=normalized_lines,
            )
            persisted_allocations = self._build_allocations(
                run_employee=run_employee,
                base_amount=base_amount,
                lines=normalized_lines,
            )

            allocation_repo.delete_all_for_payroll_run_employee(payroll_run_employee_id)
            uow.session.flush()
            for allocation in persisted_allocations:
                allocation_repo.add(allocation)

            uow.commit()
            return self._build_allocation_set_dto(run_employee, run, persisted_allocations)

    def _normalize_command_lines(
        self,
        lines: tuple[PayrollProjectAllocationLineCommand, ...],
    ) -> tuple[PayrollProjectAllocationLineCommand, ...]:
        normalized_lines: list[PayrollProjectAllocationLineCommand] = []
        for line in lines:
            project_id = self._normalize_required_id(line.project_id, "Project")
            basis_code = (line.allocation_basis_code or "").strip().lower()
            if basis_code not in _ALLOCATION_BASIS_CODES:
                raise ValidationError(
                    f"Allocation basis code must be one of: {', '.join(sorted(_ALLOCATION_BASIS_CODES))}."
                )
            quantity = self._normalize_optional_decimal(line.allocation_quantity, "Allocation quantity")
            percent = self._normalize_optional_decimal(line.allocation_percent, "Allocation percent")
            amount = self._normalize_optional_decimal(line.allocated_cost_amount, "Allocated cost amount")
            normalized_lines.append(
                PayrollProjectAllocationLineCommand(
                    project_id=project_id,
                    allocation_basis_code=basis_code,
                    contract_id=self._normalize_optional_id(line.contract_id, "Contract"),
                    project_job_id=self._normalize_optional_id(line.project_job_id, "Project job"),
                    project_cost_code_id=self._normalize_optional_id(line.project_cost_code_id, "Project cost code"),
                    allocation_quantity=quantity,
                    allocation_percent=percent,
                    allocated_cost_amount=amount,
                    notes=self._normalize_optional_text(line.notes),
                )
            )
        return tuple(normalized_lines)

    def _validate_dimensions(
        self,
        *,
        session: Session,
        company_id: int,
        lines: tuple[PayrollProjectAllocationLineCommand, ...],
    ) -> None:
        for index, line in enumerate(lines, start=1):
            self._project_dimension_validation_service.validate_line_dimensions(
                session=session,
                company_id=company_id,
                contract_id=line.contract_id,
                project_id=line.project_id,
                project_job_id=line.project_job_id,
                project_cost_code_id=line.project_cost_code_id,
                line_number=index,
            )

    def _build_allocations(
        self,
        *,
        run_employee: PayrollRunEmployee,
        base_amount: Decimal,
        lines: tuple[PayrollProjectAllocationLineCommand, ...],
    ) -> list[PayrollRunEmployeeProjectAllocation]:
        basis_codes = {line.allocation_basis_code for line in lines}
        if len(basis_codes) != 1:
            raise ValidationError("All allocation lines must use the same allocation basis in this slice.")
        basis_code = next(iter(basis_codes))

        if basis_code == "percent":
            stored_lines = self._build_percent_allocations(base_amount, lines)
        elif basis_code == "hours":
            stored_lines = self._build_hours_allocations(base_amount, lines)
        else:
            stored_lines = self._build_amount_allocations(base_amount, lines)

        allocations: list[PayrollRunEmployeeProjectAllocation] = []
        for index, stored_line in enumerate(stored_lines, start=1):
            allocations.append(
                PayrollRunEmployeeProjectAllocation(
                    payroll_run_employee_id=run_employee.id,
                    line_number=index,
                    contract_id=stored_line.contract_id,
                    project_id=stored_line.project_id,
                    project_job_id=stored_line.project_job_id,
                    project_cost_code_id=stored_line.project_cost_code_id,
                    allocation_basis_code=stored_line.allocation_basis_code,
                    allocation_quantity=stored_line.allocation_quantity,
                    allocation_percent=stored_line.allocation_percent,
                    allocated_cost_amount=stored_line.allocated_cost_amount,
                    notes=stored_line.notes,
                )
            )
        return allocations

    def _build_percent_allocations(
        self,
        base_amount: Decimal,
        lines: tuple[PayrollProjectAllocationLineCommand, ...],
    ) -> tuple[PayrollProjectAllocationLineCommand, ...]:
        total_percent = Decimal("0.0000")
        for index, line in enumerate(lines, start=1):
            if line.allocation_percent is None:
                raise ValidationError(f"Line {index}: Allocation percent is required for percent basis.")
            total_percent += line.allocation_percent
        if total_percent != _HUNDRED_PERCENT:
            raise ValidationError("Percent allocations must total exactly 100.0000.")

        return self._apply_derived_amounts(
            base_amount=base_amount,
            lines=lines,
            denominator=_HUNDRED_PERCENT,
            numerator_getter=lambda line: line.allocation_percent or Decimal("0.0000"),
        )

    def _build_hours_allocations(
        self,
        base_amount: Decimal,
        lines: tuple[PayrollProjectAllocationLineCommand, ...],
    ) -> tuple[PayrollProjectAllocationLineCommand, ...]:
        total_hours = Decimal("0.0000")
        for index, line in enumerate(lines, start=1):
            if line.allocation_quantity is None:
                raise ValidationError(f"Line {index}: Allocation quantity is required for hours basis.")
            total_hours += line.allocation_quantity
        if total_hours <= Decimal("0.0000"):
            raise ValidationError("Hours allocations must include a positive total quantity.")

        return self._apply_derived_amounts(
            base_amount=base_amount,
            lines=lines,
            denominator=total_hours,
            numerator_getter=lambda line: line.allocation_quantity or Decimal("0.0000"),
        )

    def _build_amount_allocations(
        self,
        base_amount: Decimal,
        lines: tuple[PayrollProjectAllocationLineCommand, ...],
    ) -> tuple[PayrollProjectAllocationLineCommand, ...]:
        total_amount = Decimal("0.0000")
        normalized_lines: list[PayrollProjectAllocationLineCommand] = []
        for index, line in enumerate(lines, start=1):
            if line.allocated_cost_amount is None:
                raise ValidationError(f"Line {index}: Allocated cost amount is required for amount basis.")
            total_amount += line.allocated_cost_amount
            normalized_lines.append(
                PayrollProjectAllocationLineCommand(
                    project_id=line.project_id,
                    allocation_basis_code=line.allocation_basis_code,
                    contract_id=line.contract_id,
                    project_job_id=line.project_job_id,
                    project_cost_code_id=line.project_cost_code_id,
                    allocation_quantity=line.allocation_quantity,
                    allocation_percent=line.allocation_percent,
                    allocated_cost_amount=line.allocated_cost_amount,
                    notes=line.notes,
                )
            )
        if total_amount != base_amount:
            raise ValidationError("Amount allocations must total the payroll allocation base exactly.")
        return tuple(normalized_lines)

    def _apply_derived_amounts(
        self,
        *,
        base_amount: Decimal,
        lines: tuple[PayrollProjectAllocationLineCommand, ...],
        denominator: Decimal,
        numerator_getter: Callable[[PayrollProjectAllocationLineCommand], Decimal],
    ) -> tuple[PayrollProjectAllocationLineCommand, ...]:
        derived_lines: list[PayrollProjectAllocationLineCommand] = []
        remaining = base_amount
        last_index = len(lines) - 1
        for index, line in enumerate(lines):
            if index == last_index:
                derived_amount = remaining
            else:
                raw_amount = (base_amount * numerator_getter(line)) / denominator
                derived_amount = raw_amount.quantize(_MONEY_SCALE, rounding=ROUND_HALF_UP)
                remaining -= derived_amount
            derived_lines.append(
                PayrollProjectAllocationLineCommand(
                    project_id=line.project_id,
                    allocation_basis_code=line.allocation_basis_code,
                    contract_id=line.contract_id,
                    project_job_id=line.project_job_id,
                    project_cost_code_id=line.project_cost_code_id,
                    allocation_quantity=line.allocation_quantity,
                    allocation_percent=line.allocation_percent,
                    allocated_cost_amount=derived_amount,
                    notes=line.notes,
                )
            )
        return tuple(derived_lines)

    def _require_run_employee_context(
        self,
        *,
        session: Session,
        company_id: int,
        payroll_run_employee_id: int,
    ) -> tuple[PayrollRunEmployee, PayrollRun]:
        run_employee_repo = self._run_employee_repository_factory(session)
        run_employee = run_employee_repo.get_by_id(company_id, payroll_run_employee_id)
        if run_employee is None:
            raise NotFoundError("Payroll run employee was not found.")
        run = self._run_repository_factory(session).get_by_id(company_id, run_employee.run_id)
        if run is None:
            raise NotFoundError("Payroll run was not found for the selected employee.")
        return run_employee, run

    def _build_allocation_set_dto(
        self,
        run_employee: PayrollRunEmployee,
        run: PayrollRun,
        allocations: list[PayrollRunEmployeeProjectAllocation],
    ) -> PayrollProjectAllocationSetDTO:
        base_amount = self._get_allocation_base_amount(run_employee)
        total_allocated = sum(
            (Decimal(str(allocation.allocated_cost_amount)) for allocation in allocations),
            Decimal("0.0000"),
        )
        line_dtos = tuple(self._to_line_dto(allocation) for allocation in allocations)
        employee = run_employee.employee
        return PayrollProjectAllocationSetDTO(
            payroll_run_employee_id=run_employee.id,
            run_id=run.id,
            run_reference=run.run_reference,
            run_status_code=run.status_code,
            employee_id=run_employee.employee_id,
            employee_number=employee.employee_number if employee else "",
            employee_display_name=employee.display_name if employee else "",
            employee_status_code=run_employee.status_code,
            allocation_base_code="employer_cost_base",
            allocation_base_amount=base_amount,
            total_allocated_amount=total_allocated,
            remaining_unallocated_amount=(base_amount - total_allocated).quantize(_MONEY_SCALE),
            editable=self._is_editable(run_employee, run),
            lines=line_dtos,
        )

    def _to_line_dto(
        self,
        allocation: PayrollRunEmployeeProjectAllocation,
    ) -> PayrollProjectAllocationLineDTO:
        contract = allocation.contract
        project = allocation.project
        job = allocation.project_job
        cost_code = allocation.project_cost_code
        return PayrollProjectAllocationLineDTO(
            id=allocation.id,
            line_number=allocation.line_number,
            contract_id=allocation.contract_id,
            contract_number=contract.contract_number if contract else None,
            project_id=allocation.project_id,
            project_code=project.project_code if project else "",
            project_name=project.project_name if project else "",
            project_job_id=allocation.project_job_id,
            project_job_code=job.job_code if job else None,
            project_job_name=job.job_name if job else None,
            project_cost_code_id=allocation.project_cost_code_id,
            project_cost_code_code=cost_code.code if cost_code else None,
            project_cost_code_name=cost_code.name if cost_code else None,
            allocation_basis_code=allocation.allocation_basis_code,
            allocation_quantity=(
                Decimal(str(allocation.allocation_quantity))
                if allocation.allocation_quantity is not None
                else None
            ),
            allocation_percent=(
                Decimal(str(allocation.allocation_percent))
                if allocation.allocation_percent is not None
                else None
            ),
            allocated_cost_amount=Decimal(str(allocation.allocated_cost_amount)),
            notes=allocation.notes,
            created_at=allocation.created_at,
        )

    def _get_allocation_base_amount(self, run_employee: PayrollRunEmployee) -> Decimal:
        return Decimal(str(run_employee.employer_cost_base)).quantize(_MONEY_SCALE)

    def _assert_editable(self, run_employee: PayrollRunEmployee, run: PayrollRun) -> None:
        if not self._is_editable(run_employee, run):
            raise ValidationError(
                "Project allocations can only be edited while the payroll run is draft or calculated and the employee row is included."
            )

    def _is_editable(self, run_employee: PayrollRunEmployee, run: PayrollRun) -> bool:
        return run.status_code in _EDITABLE_RUN_STATUSES and run_employee.status_code == "included"

    def _normalize_required_id(self, value: int, label: str) -> int:
        if value <= 0:
            raise ValidationError(f"{label} is required.")
        return value

    def _normalize_optional_id(self, value: int | None, label: str) -> int | None:
        if value is None:
            return None
        if value <= 0:
            raise ValidationError(f"{label} identifiers must be greater than zero.")
        return value

    def _normalize_optional_decimal(self, value: Decimal | None, label: str) -> Decimal | None:
        if value is None:
            return None
        if value < Decimal("0"):
            raise ValidationError(f"{label} cannot be negative.")
        return value.quantize(_MONEY_SCALE, rounding=ROUND_HALF_UP)

    def _normalize_optional_text(self, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None