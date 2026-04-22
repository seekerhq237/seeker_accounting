from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.payroll.models.employee import Employee


class EmployeeRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(
        self,
        company_id: int,
        active_only: bool = False,
        query: str | None = None,
        department_id: int | None = None,
        position_id: int | None = None,
    ) -> list[Employee]:
        stmt = (
            select(Employee)
            .where(Employee.company_id == company_id)
            .options(selectinload(Employee.department), selectinload(Employee.position))
            .order_by(Employee.employee_number)
        )
        if active_only:
            stmt = stmt.where(Employee.is_active == True)  # noqa: E712
        if query:
            like = f"%{query}%"
            stmt = stmt.where(
                or_(
                    Employee.employee_number.ilike(like),
                    Employee.display_name.ilike(like),
                    Employee.first_name.ilike(like),
                    Employee.last_name.ilike(like),
                )
            )
        if department_id is not None:
            stmt = stmt.where(Employee.department_id == department_id)
        if position_id is not None:
            stmt = stmt.where(Employee.position_id == position_id)
        return list(self._session.scalars(stmt).all())

    def get_by_id(self, company_id: int, employee_id: int) -> Employee | None:
        stmt = (
            select(Employee)
            .where(Employee.id == employee_id)
            .where(Employee.company_id == company_id)
            .options(selectinload(Employee.department), selectinload(Employee.position))
        )
        return self._session.scalar(stmt)

    def get_by_number(self, company_id: int, employee_number: str) -> Employee | None:
        stmt = (
            select(Employee)
            .where(Employee.company_id == company_id)
            .where(Employee.employee_number == employee_number)
        )
        return self._session.scalar(stmt)

    def save(self, employee: Employee) -> Employee:
        self._session.add(employee)
        return employee
