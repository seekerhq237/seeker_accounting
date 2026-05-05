from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.payroll.models.payroll_run import PayrollRun
from seeker_accounting.modules.payroll.models.payroll_run_employee import PayrollRunEmployee
from seeker_accounting.modules.payroll.models.payroll_run_line import PayrollRunLine


class PayrollRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(
        self,
        company_id: int,
        status_code: str | None = None,
    ) -> list[PayrollRun]:
        stmt = (
            select(PayrollRun)
            .where(PayrollRun.company_id == company_id)
            .order_by(PayrollRun.period_year.desc(), PayrollRun.period_month.desc())
        )
        if status_code is not None:
            stmt = stmt.where(PayrollRun.status_code == status_code)
        return list(self._session.scalars(stmt).all())

    def list_by_period(
        self, company_id: int, period_year: int, period_month: int
    ) -> list[PayrollRun]:
        stmt = (
            select(PayrollRun)
            .where(
                PayrollRun.company_id == company_id,
                PayrollRun.period_year == period_year,
                PayrollRun.period_month == period_month,
            )
            .order_by(PayrollRun.run_type_code, PayrollRun.run_sequence)
        )
        return list(self._session.scalars(stmt).all())

    def get_by_id(self, company_id: int, run_id: int) -> PayrollRun | None:
        stmt = (
            select(PayrollRun)
            .where(
                PayrollRun.id == run_id,
                PayrollRun.company_id == company_id,
            )
        )
        return self._session.scalar(stmt)

    def get_by_period(
        self, company_id: int, period_year: int, period_month: int
    ) -> PayrollRun | None:
        return self.get_regular_by_period(company_id, period_year, period_month)

    def get_regular_by_period(
        self, company_id: int, period_year: int, period_month: int
    ) -> PayrollRun | None:
        stmt = select(PayrollRun).where(
            PayrollRun.company_id == company_id,
            PayrollRun.period_year == period_year,
            PayrollRun.period_month == period_month,
            PayrollRun.run_type_code == "regular",
        )
        return self._session.scalars(stmt.order_by(PayrollRun.run_sequence.desc())).first()

    def get_active_regular_by_period(
        self, company_id: int, period_year: int, period_month: int
    ) -> PayrollRun | None:
        stmt = select(PayrollRun).where(
            PayrollRun.company_id == company_id,
            PayrollRun.period_year == period_year,
            PayrollRun.period_month == period_month,
            PayrollRun.run_type_code == "regular",
            PayrollRun.status_code != "voided",
        )
        return self._session.scalars(stmt.order_by(PayrollRun.run_sequence.desc())).first()

    def next_run_sequence(
        self, company_id: int, period_year: int, period_month: int, run_type_code: str
    ) -> int:
        stmt = select(func.max(PayrollRun.run_sequence)).where(
            PayrollRun.company_id == company_id,
            PayrollRun.period_year == period_year,
            PayrollRun.period_month == period_month,
            PayrollRun.run_type_code == run_type_code,
        )
        return int(self._session.scalar(stmt) or 0) + 1

    def check_reference_exists(
        self, company_id: int, run_reference: str, exclude_id: int | None = None
    ) -> bool:
        stmt = select(PayrollRun.id).where(
            PayrollRun.company_id == company_id,
            PayrollRun.run_reference == run_reference,
        )
        if exclude_id is not None:
            stmt = stmt.where(PayrollRun.id != exclude_id)
        return self._session.scalar(stmt) is not None

    def save(self, run: PayrollRun) -> PayrollRun:
        self._session.add(run)
        return run


class PayrollRunEmployeeRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_run(
        self,
        company_id: int,
        run_id: int,
    ) -> list[PayrollRunEmployee]:
        stmt = (
            select(PayrollRunEmployee)
            .where(
                PayrollRunEmployee.company_id == company_id,
                PayrollRunEmployee.run_id == run_id,
            )
            .options(selectinload(PayrollRunEmployee.employee))
            .order_by(PayrollRunEmployee.employee_id)
        )
        return list(self._session.scalars(stmt).all())

    def get_by_id(
        self, company_id: int, run_employee_id: int
    ) -> PayrollRunEmployee | None:
        stmt = (
            select(PayrollRunEmployee)
            .where(
                PayrollRunEmployee.id == run_employee_id,
                PayrollRunEmployee.company_id == company_id,
            )
            .options(
                selectinload(PayrollRunEmployee.employee),
                selectinload(PayrollRunEmployee.lines).selectinload(PayrollRunLine.component),
            )
        )
        return self._session.scalar(stmt)

    def get_by_employee(
        self, company_id: int, run_id: int, employee_id: int
    ) -> PayrollRunEmployee | None:
        stmt = select(PayrollRunEmployee).where(
            PayrollRunEmployee.company_id == company_id,
            PayrollRunEmployee.run_id == run_id,
            PayrollRunEmployee.employee_id == employee_id,
        )
        return self._session.scalar(stmt)

    def delete_all_for_run(self, run_id: int) -> None:
        """Delete all employee rows for a run (used when recalculating)."""
        stmt = select(PayrollRunEmployee).where(PayrollRunEmployee.run_id == run_id)
        for row in self._session.scalars(stmt).all():
            self._session.delete(row)

    def list_with_lines_by_run(
        self,
        company_id: int,
        run_id: int,
    ) -> list[PayrollRunEmployee]:
        stmt = (
            select(PayrollRunEmployee)
            .where(
                PayrollRunEmployee.company_id == company_id,
                PayrollRunEmployee.run_id == run_id,
            )
            .options(
                selectinload(PayrollRunEmployee.employee),
                selectinload(PayrollRunEmployee.lines).selectinload(PayrollRunLine.component),
            )
            .order_by(PayrollRunEmployee.employee_id)
        )
        return list(self._session.scalars(stmt).all())

    def save(self, run_employee: PayrollRunEmployee) -> PayrollRunEmployee:
        self._session.add(run_employee)
        return run_employee
