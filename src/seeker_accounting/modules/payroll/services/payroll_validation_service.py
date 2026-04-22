"""PayrollValidationService — pre-run validation checks for a payroll period.

Validates that all required employee setup is in place before a payroll run
is triggered. Returns a structured validation result that the UI can display.
"""

from __future__ import annotations

from datetime import date
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.payroll.dto.payroll_calculation_dto import (
    PayrollValidationIssueDTO,
    PayrollValidationResultDTO,
)
from seeker_accounting.modules.payroll.repositories.compensation_profile_repository import (
    CompensationProfileRepository,
)
from seeker_accounting.modules.payroll.repositories.component_assignment_repository import (
    ComponentAssignmentRepository,
)
from seeker_accounting.modules.payroll.repositories.employee_repository import EmployeeRepository

CompensationProfileRepositoryFactory = Callable[[Session], CompensationProfileRepository]
ComponentAssignmentRepositoryFactory = Callable[[Session], ComponentAssignmentRepository]
EmployeeRepositoryFactory = Callable[[Session], EmployeeRepository]


class PayrollValidationService:
    """Pre-run validation: check all employees have compensation profiles and assignments."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        employee_repository_factory: EmployeeRepositoryFactory,
        profile_repository_factory: CompensationProfileRepositoryFactory,
        assignment_repository_factory: ComponentAssignmentRepositoryFactory,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._employee_repo_factory = employee_repository_factory
        self._profile_repo_factory = profile_repository_factory
        self._assignment_repo_factory = assignment_repository_factory

    def validate_for_period(
        self,
        company_id: int,
        period_year: int,
        period_month: int,
    ) -> PayrollValidationResultDTO:
        period_date = date(period_year, period_month, 1)

        with self._uow_factory() as uow:
            emp_repo = self._employee_repo_factory(uow.session)
            profile_repo = self._profile_repo_factory(uow.session)
            assignment_repo = self._assignment_repo_factory(uow.session)

            employees = emp_repo.list_by_company(company_id, active_only=True)
            issues: list[PayrollValidationIssueDTO] = []

            for emp in employees:
                # Check compensation profile
                profile = profile_repo.get_active_for_period(
                    company_id, emp.id, period_date
                )
                if profile is None:
                    issues.append(
                        PayrollValidationIssueDTO(
                            employee_id=emp.id,
                            employee_display_name=emp.display_name,
                            issue_code="NO_COMPENSATION_PROFILE",
                            issue_message=(
                                f"{emp.display_name} has no active compensation profile "
                                f"covering {period_year}-{period_month:02d}."
                            ),
                            severity="error",
                        )
                    )

                # Check at least one component assignment
                assignments = assignment_repo.get_active_for_period(
                    company_id, emp.id, period_date
                )
                if not assignments:
                    issues.append(
                        PayrollValidationIssueDTO(
                            employee_id=emp.id,
                            employee_display_name=emp.display_name,
                            issue_code="NO_COMPONENT_ASSIGNMENTS",
                            issue_message=(
                                f"{emp.display_name} has no active payroll component "
                                f"assignments for {period_year}-{period_month:02d}."
                            ),
                            severity="warning",
                        )
                    )

            return PayrollValidationResultDTO(
                company_id=company_id,
                period_year=period_year,
                period_month=period_month,
                employee_count=len(employees),
                issues=issues,
            )
