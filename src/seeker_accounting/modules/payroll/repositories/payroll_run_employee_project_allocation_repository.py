from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.payroll.models.payroll_run_employee_project_allocation import (
    PayrollRunEmployeeProjectAllocation,
)


class PayrollRunEmployeeProjectAllocationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, allocation_id: int) -> PayrollRunEmployeeProjectAllocation | None:
        stmt = (
            select(PayrollRunEmployeeProjectAllocation)
            .where(PayrollRunEmployeeProjectAllocation.id == allocation_id)
            .options(
                selectinload(PayrollRunEmployeeProjectAllocation.contract),
                selectinload(PayrollRunEmployeeProjectAllocation.project),
                selectinload(PayrollRunEmployeeProjectAllocation.project_job),
                selectinload(PayrollRunEmployeeProjectAllocation.project_cost_code),
            )
        )
        return self._session.scalar(stmt)

    def list_by_payroll_run_employee(
        self,
        payroll_run_employee_id: int,
    ) -> list[PayrollRunEmployeeProjectAllocation]:
        stmt = (
            select(PayrollRunEmployeeProjectAllocation)
            .where(PayrollRunEmployeeProjectAllocation.payroll_run_employee_id == payroll_run_employee_id)
            .options(
                selectinload(PayrollRunEmployeeProjectAllocation.contract),
                selectinload(PayrollRunEmployeeProjectAllocation.project),
                selectinload(PayrollRunEmployeeProjectAllocation.project_job),
                selectinload(PayrollRunEmployeeProjectAllocation.project_cost_code),
            )
            .order_by(PayrollRunEmployeeProjectAllocation.line_number)
        )
        return list(self._session.scalars(stmt).all())

    def add(
        self,
        allocation: PayrollRunEmployeeProjectAllocation,
    ) -> PayrollRunEmployeeProjectAllocation:
        self._session.add(allocation)
        return allocation

    def save(
        self,
        allocation: PayrollRunEmployeeProjectAllocation,
    ) -> PayrollRunEmployeeProjectAllocation:
        self._session.add(allocation)
        return allocation

    def delete(self, allocation: PayrollRunEmployeeProjectAllocation) -> None:
        self._session.delete(allocation)

    def delete_all_for_payroll_run_employee(self, payroll_run_employee_id: int) -> None:
        stmt = select(PayrollRunEmployeeProjectAllocation).where(
            PayrollRunEmployeeProjectAllocation.payroll_run_employee_id == payroll_run_employee_id
        )
        for row in self._session.scalars(stmt).all():
            self._session.delete(row)

    def sum_allocated_amount_by_payroll_run_employee(self, payroll_run_employee_id: int) -> Decimal:
        result = self._session.scalar(
            select(
                func.coalesce(
                    func.sum(PayrollRunEmployeeProjectAllocation.allocated_cost_amount),
                    0,
                )
            ).where(PayrollRunEmployeeProjectAllocation.payroll_run_employee_id == payroll_run_employee_id)
        )
        return Decimal(str(result)) if result is not None else Decimal("0")