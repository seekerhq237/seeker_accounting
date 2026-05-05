from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.payroll.models.employee_payroll_correction import (
    EmployeePayrollCorrection,
)


class EmployeePayrollCorrectionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, company_id: int, correction_id: int) -> EmployeePayrollCorrection | None:
        stmt = (
            select(EmployeePayrollCorrection)
            .where(
                EmployeePayrollCorrection.id == correction_id,
                EmployeePayrollCorrection.company_id == company_id,
            )
            .options(
                selectinload(EmployeePayrollCorrection.employee),
                selectinload(EmployeePayrollCorrection.component),
            )
        )
        return self._session.scalar(stmt)

    def list_by_company(
        self, company_id: int, status_code: str | None = None
    ) -> list[EmployeePayrollCorrection]:
        stmt = (
            select(EmployeePayrollCorrection)
            .where(EmployeePayrollCorrection.company_id == company_id)
            .options(
                selectinload(EmployeePayrollCorrection.employee),
                selectinload(EmployeePayrollCorrection.component),
            )
            .order_by(
                EmployeePayrollCorrection.period_year.desc(),
                EmployeePayrollCorrection.period_month.desc(),
                EmployeePayrollCorrection.id.desc(),
            )
        )
        if status_code is not None:
            stmt = stmt.where(EmployeePayrollCorrection.status_code == status_code)
        return list(self._session.scalars(stmt).all())

    def list_pending_for_period(
        self,
        company_id: int,
        period_year: int,
        period_month: int,
        employee_ids: tuple[int, ...] | None = None,
    ) -> list[EmployeePayrollCorrection]:
        stmt = (
            select(EmployeePayrollCorrection)
            .where(
                EmployeePayrollCorrection.company_id == company_id,
                EmployeePayrollCorrection.status_code == "pending",
                or_(
                    EmployeePayrollCorrection.period_year < period_year,
                    (
                        (EmployeePayrollCorrection.period_year == period_year)
                        & (EmployeePayrollCorrection.period_month <= period_month)
                    ),
                ),
            )
            .options(
                selectinload(EmployeePayrollCorrection.employee),
                selectinload(EmployeePayrollCorrection.component),
            )
            .order_by(EmployeePayrollCorrection.period_year, EmployeePayrollCorrection.period_month, EmployeePayrollCorrection.id)
        )
        if employee_ids:
            stmt = stmt.where(EmployeePayrollCorrection.employee_id.in_(employee_ids))
        return list(self._session.scalars(stmt).all())

    def save(self, correction: EmployeePayrollCorrection) -> EmployeePayrollCorrection:
        self._session.add(correction)
        return correction
