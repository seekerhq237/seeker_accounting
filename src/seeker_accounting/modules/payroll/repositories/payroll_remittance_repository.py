from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.payroll.models.payroll_remittance_batch import PayrollRemittanceBatch
from seeker_accounting.modules.payroll.models.payroll_remittance_line import PayrollRemittanceLine


class PayrollRemittanceBatchRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(
        self,
        company_id: int,
        authority_code: str | None = None,
        status_code: str | None = None,
    ) -> list[PayrollRemittanceBatch]:
        stmt = (
            select(PayrollRemittanceBatch)
            .where(PayrollRemittanceBatch.company_id == company_id)
            .order_by(
                PayrollRemittanceBatch.period_start_date.desc(),
                PayrollRemittanceBatch.id.desc(),
            )
        )
        if authority_code:
            stmt = stmt.where(
                PayrollRemittanceBatch.remittance_authority_code == authority_code
            )
        if status_code:
            stmt = stmt.where(PayrollRemittanceBatch.status_code == status_code)
        return list(self._session.scalars(stmt).all())

    def list_by_run(self, company_id: int, run_id: int) -> list[PayrollRemittanceBatch]:
        stmt = (
            select(PayrollRemittanceBatch)
            .where(
                PayrollRemittanceBatch.company_id == company_id,
                PayrollRemittanceBatch.payroll_run_id == run_id,
            )
            .order_by(PayrollRemittanceBatch.id)
        )
        return list(self._session.scalars(stmt).all())

    def get_by_id(
        self, company_id: int, batch_id: int
    ) -> PayrollRemittanceBatch | None:
        stmt = (
            select(PayrollRemittanceBatch)
            .where(
                PayrollRemittanceBatch.id == batch_id,
                PayrollRemittanceBatch.company_id == company_id,
            )
            .options(
                selectinload(PayrollRemittanceBatch.lines).selectinload(
                    PayrollRemittanceLine.payroll_component
                ),
                selectinload(PayrollRemittanceBatch.lines).selectinload(
                    PayrollRemittanceLine.liability_account
                ),
            )
        )
        return self._session.scalar(stmt)

    def check_batch_number_exists(
        self, company_id: int, batch_number: str, exclude_id: int | None = None
    ) -> bool:
        stmt = select(PayrollRemittanceBatch.id).where(
            PayrollRemittanceBatch.company_id == company_id,
            PayrollRemittanceBatch.batch_number == batch_number,
        )
        if exclude_id is not None:
            stmt = stmt.where(PayrollRemittanceBatch.id != exclude_id)
        return self._session.scalar(stmt) is not None

    def save(self, batch: PayrollRemittanceBatch) -> PayrollRemittanceBatch:
        self._session.add(batch)
        return batch


class PayrollRemittanceLineRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, line_id: int) -> PayrollRemittanceLine | None:
        return self._session.get(PayrollRemittanceLine, line_id)

    def list_by_batch(self, batch_id: int) -> list[PayrollRemittanceLine]:
        stmt = (
            select(PayrollRemittanceLine)
            .where(PayrollRemittanceLine.payroll_remittance_batch_id == batch_id)
            .options(
                selectinload(PayrollRemittanceLine.payroll_component),
                selectinload(PayrollRemittanceLine.liability_account),
            )
            .order_by(PayrollRemittanceLine.line_number)
        )
        return list(self._session.scalars(stmt).all())

    def next_line_number(self, batch_id: int) -> int:
        existing = self.list_by_batch(batch_id)
        if not existing:
            return 1
        return max(ln.line_number for ln in existing) + 1

    def save(self, line: PayrollRemittanceLine) -> PayrollRemittanceLine:
        self._session.add(line)
        return line

    def delete(self, line: PayrollRemittanceLine) -> None:
        self._session.delete(line)
