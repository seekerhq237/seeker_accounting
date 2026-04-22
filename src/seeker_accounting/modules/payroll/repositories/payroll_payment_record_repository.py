from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.payroll.models.payroll_payment_record import PayrollPaymentRecord


class PayrollPaymentRecordRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_run_employee(
        self, company_id: int, run_employee_id: int
    ) -> list[PayrollPaymentRecord]:
        stmt = (
            select(PayrollPaymentRecord)
            .where(
                PayrollPaymentRecord.company_id == company_id,
                PayrollPaymentRecord.run_employee_id == run_employee_id,
            )
            .order_by(PayrollPaymentRecord.payment_date, PayrollPaymentRecord.id)
        )
        return list(self._session.scalars(stmt).all())

    def list_by_run(self, company_id: int, run_id: int) -> list[PayrollPaymentRecord]:
        """Load all payment records for all employees in a given run."""
        from seeker_accounting.modules.payroll.models.payroll_run_employee import (
            PayrollRunEmployee,
        )

        stmt = (
            select(PayrollPaymentRecord)
            .join(
                PayrollRunEmployee,
                PayrollPaymentRecord.run_employee_id == PayrollRunEmployee.id,
            )
            .where(
                PayrollPaymentRecord.company_id == company_id,
                PayrollRunEmployee.run_id == run_id,
            )
            .order_by(PayrollPaymentRecord.payment_date, PayrollPaymentRecord.id)
        )
        return list(self._session.scalars(stmt).all())

    def get_by_id(self, company_id: int, record_id: int) -> PayrollPaymentRecord | None:
        stmt = select(PayrollPaymentRecord).where(
            PayrollPaymentRecord.id == record_id,
            PayrollPaymentRecord.company_id == company_id,
        )
        return self._session.scalar(stmt)

    def save(self, record: PayrollPaymentRecord) -> PayrollPaymentRecord:
        self._session.add(record)
        return record

    def delete(self, record: PayrollPaymentRecord) -> None:
        self._session.delete(record)
