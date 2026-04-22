from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.payroll.models.employee_component_assignment import (
    EmployeeComponentAssignment,
)


class ComponentAssignmentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(
        self,
        company_id: int,
        active_only: bool = False,
    ) -> list[EmployeeComponentAssignment]:
        stmt = (
            select(EmployeeComponentAssignment)
            .where(EmployeeComponentAssignment.company_id == company_id)
            .options(
                selectinload(EmployeeComponentAssignment.component),
                selectinload(EmployeeComponentAssignment.employee),
            )
            .order_by(
                EmployeeComponentAssignment.employee_id,
                EmployeeComponentAssignment.component_id,
                EmployeeComponentAssignment.effective_from.desc(),
            )
        )
        if active_only:
            stmt = stmt.where(EmployeeComponentAssignment.is_active == True)  # noqa: E712
        return list(self._session.scalars(stmt).all())

    def list_by_employee(
        self,
        company_id: int,
        employee_id: int,
        active_only: bool = False,
    ) -> list[EmployeeComponentAssignment]:
        stmt = (
            select(EmployeeComponentAssignment)
            .where(
                EmployeeComponentAssignment.company_id == company_id,
                EmployeeComponentAssignment.employee_id == employee_id,
            )
            .options(
                selectinload(EmployeeComponentAssignment.component),
                selectinload(EmployeeComponentAssignment.employee),
            )
            .order_by(EmployeeComponentAssignment.component_id, EmployeeComponentAssignment.effective_from.desc())
        )
        if active_only:
            stmt = stmt.where(EmployeeComponentAssignment.is_active == True)  # noqa: E712
        return list(self._session.scalars(stmt).all())

    def get_by_id(
        self, company_id: int, assignment_id: int
    ) -> EmployeeComponentAssignment | None:
        stmt = (
            select(EmployeeComponentAssignment)
            .where(
                EmployeeComponentAssignment.id == assignment_id,
                EmployeeComponentAssignment.company_id == company_id,
            )
            .options(
                selectinload(EmployeeComponentAssignment.component),
                selectinload(EmployeeComponentAssignment.employee),
            )
        )
        return self._session.scalar(stmt)

    def get_active_for_period(
        self,
        company_id: int,
        employee_id: int,
        period_date: date,
    ) -> list[EmployeeComponentAssignment]:
        """Return all active assignments covering period_date for this employee."""
        stmt = (
            select(EmployeeComponentAssignment)
            .where(
                EmployeeComponentAssignment.company_id == company_id,
                EmployeeComponentAssignment.employee_id == employee_id,
                EmployeeComponentAssignment.is_active == True,  # noqa: E712
                EmployeeComponentAssignment.effective_from <= period_date,
            )
            .options(selectinload(EmployeeComponentAssignment.component))
        )
        assignments = list(self._session.scalars(stmt).all())
        return [
            a for a in assignments
            if a.effective_to is None or a.effective_to >= period_date
        ]

    def check_duplicate(
        self,
        company_id: int,
        employee_id: int,
        component_id: int,
        effective_from: date,
        exclude_id: int | None = None,
    ) -> bool:
        stmt = select(EmployeeComponentAssignment.id).where(
            EmployeeComponentAssignment.company_id == company_id,
            EmployeeComponentAssignment.employee_id == employee_id,
            EmployeeComponentAssignment.component_id == component_id,
            EmployeeComponentAssignment.effective_from == effective_from,
        )
        if exclude_id is not None:
            stmt = stmt.where(EmployeeComponentAssignment.id != exclude_id)
        return self._session.scalar(stmt) is not None

    def save(self, assignment: EmployeeComponentAssignment) -> EmployeeComponentAssignment:
        self._session.add(assignment)
        return assignment
