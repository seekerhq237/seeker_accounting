from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.payroll.models.department import Department


class DepartmentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(self, company_id: int, active_only: bool = False) -> list[Department]:
        stmt = (
            select(Department)
            .where(Department.company_id == company_id)
            .order_by(Department.code)
        )
        if active_only:
            stmt = stmt.where(Department.is_active == True)  # noqa: E712
        return list(self._session.scalars(stmt).all())

    def get_by_id(self, company_id: int, department_id: int) -> Department | None:
        stmt = (
            select(Department)
            .where(Department.id == department_id)
            .where(Department.company_id == company_id)
        )
        return self._session.scalar(stmt)

    def get_by_code(self, company_id: int, code: str) -> Department | None:
        stmt = (
            select(Department)
            .where(Department.company_id == company_id)
            .where(Department.code == code)
        )
        return self._session.scalar(stmt)

    def save(self, department: Department) -> Department:
        self._session.add(department)
        return department
