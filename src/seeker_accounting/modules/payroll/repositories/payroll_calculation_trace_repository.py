from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.payroll.models.payroll_calculation_trace import (
    PayrollCalculationTrace,
)


class PayrollCalculationTraceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def delete_all_for_run(self, run_id: int) -> None:
        stmt = select(PayrollCalculationTrace).where(PayrollCalculationTrace.run_id == run_id)
        for row in self._session.scalars(stmt).all():
            self._session.delete(row)

    def list_by_run_employee(
        self, company_id: int, run_employee_id: int
    ) -> list[PayrollCalculationTrace]:
        stmt = (
            select(PayrollCalculationTrace)
            .where(
                PayrollCalculationTrace.company_id == company_id,
                PayrollCalculationTrace.run_employee_id == run_employee_id,
            )
            .options(selectinload(PayrollCalculationTrace.component))
            .order_by(PayrollCalculationTrace.sequence_number)
        )
        return list(self._session.scalars(stmt).all())

    def save_many(self, traces: list[PayrollCalculationTrace]) -> None:
        self._session.add_all(traces)
