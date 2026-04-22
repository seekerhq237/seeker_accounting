from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.payroll.models.payroll_input_batch import PayrollInputBatch
from seeker_accounting.modules.payroll.models.payroll_input_line import PayrollInputLine


class PayrollInputBatchRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(
        self,
        company_id: int,
        period_year: int | None = None,
        period_month: int | None = None,
        status_code: str | None = None,
    ) -> list[PayrollInputBatch]:
        stmt = (
            select(PayrollInputBatch)
            .where(PayrollInputBatch.company_id == company_id)
            .order_by(
                PayrollInputBatch.period_year.desc(),
                PayrollInputBatch.period_month.desc(),
                PayrollInputBatch.id.desc(),
            )
        )
        if period_year is not None:
            stmt = stmt.where(PayrollInputBatch.period_year == period_year)
        if period_month is not None:
            stmt = stmt.where(PayrollInputBatch.period_month == period_month)
        if status_code is not None:
            stmt = stmt.where(PayrollInputBatch.status_code == status_code)
        return list(self._session.scalars(stmt).all())

    def get_by_id(self, company_id: int, batch_id: int) -> PayrollInputBatch | None:
        stmt = (
            select(PayrollInputBatch)
            .where(
                PayrollInputBatch.id == batch_id,
                PayrollInputBatch.company_id == company_id,
            )
            .options(
                selectinload(PayrollInputBatch.lines).selectinload(PayrollInputLine.employee),
                selectinload(PayrollInputBatch.lines).selectinload(PayrollInputLine.component),
            )
        )
        return self._session.scalar(stmt)

    def get_approved_for_period(
        self,
        company_id: int,
        period_year: int,
        period_month: int,
    ) -> list[PayrollInputBatch]:
        """Return all approved batches for the given pay period."""
        stmt = (
            select(PayrollInputBatch)
            .where(
                PayrollInputBatch.company_id == company_id,
                PayrollInputBatch.period_year == period_year,
                PayrollInputBatch.period_month == period_month,
                PayrollInputBatch.status_code == "approved",
            )
            .options(
                selectinload(PayrollInputBatch.lines).selectinload(PayrollInputLine.component),
            )
        )
        return list(self._session.scalars(stmt).all())

    def check_reference_exists(
        self, company_id: int, batch_reference: str, exclude_id: int | None = None
    ) -> bool:
        stmt = select(PayrollInputBatch.id).where(
            PayrollInputBatch.company_id == company_id,
            PayrollInputBatch.batch_reference == batch_reference,
        )
        if exclude_id is not None:
            stmt = stmt.where(PayrollInputBatch.id != exclude_id)
        return self._session.scalar(stmt) is not None

    def save(self, batch: PayrollInputBatch) -> PayrollInputBatch:
        self._session.add(batch)
        return batch


class PayrollInputLineRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_batch(self, company_id: int, batch_id: int) -> list[PayrollInputLine]:
        stmt = (
            select(PayrollInputLine)
            .where(
                PayrollInputLine.company_id == company_id,
                PayrollInputLine.batch_id == batch_id,
            )
            .options(
                selectinload(PayrollInputLine.employee),
                selectinload(PayrollInputLine.component),
            )
            .order_by(PayrollInputLine.employee_id, PayrollInputLine.component_id)
        )
        return list(self._session.scalars(stmt).all())

    def get_by_id(self, company_id: int, line_id: int) -> PayrollInputLine | None:
        stmt = (
            select(PayrollInputLine)
            .where(
                PayrollInputLine.id == line_id,
                PayrollInputLine.company_id == company_id,
            )
        )
        return self._session.scalar(stmt)

    def save(self, line: PayrollInputLine) -> PayrollInputLine:
        self._session.add(line)
        return line

    def delete(self, line: PayrollInputLine) -> None:
        self._session.delete(line)
