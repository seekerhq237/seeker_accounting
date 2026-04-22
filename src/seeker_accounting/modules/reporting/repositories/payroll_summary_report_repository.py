from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.payroll.models.employee import Employee
from seeker_accounting.modules.payroll.models.payroll_payment_record import PayrollPaymentRecord
from seeker_accounting.modules.payroll.models.payroll_remittance_batch import PayrollRemittanceBatch
from seeker_accounting.modules.payroll.models.payroll_run import PayrollRun
from seeker_accounting.modules.payroll.models.payroll_run_employee import PayrollRunEmployee


@dataclass(frozen=True, slots=True)
class PayrollSummaryRunRow:
    run_id: int
    run_reference: str
    run_label: str
    period_year: int
    period_month: int
    run_date: date
    payment_date: date | None
    status_code: str
    employee_count: int
    gross_pay: Decimal
    deductions: Decimal
    employer_cost: Decimal
    net_pay: Decimal
    total_paid: Decimal
    outstanding_net_pay: Decimal
    journal_entry_id: int | None


@dataclass(frozen=True, slots=True)
class PayrollSummaryEmployeeRow:
    employee_id: int
    employee_number: str
    employee_name: str
    run_id: int | None
    run_employee_id: int | None
    gross_pay: Decimal
    deductions: Decimal
    employer_cost: Decimal
    net_pay: Decimal


@dataclass(frozen=True, slots=True)
class PayrollSummaryStatutoryRow:
    authority_code: str
    total_due: Decimal
    total_remitted: Decimal
    batch_count: int


class PayrollSummaryReportRepository:
    """Query-only repository for operational payroll summaries."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_run_rows(
        self,
        company_id: int,
        date_from: date | None,
        date_to: date | None,
        run_id: int | None = None,
    ) -> list[PayrollSummaryRunRow]:
        employee_totals_subquery = (
            select(
                PayrollRunEmployee.run_id.label("run_id"),
                func.count(PayrollRunEmployee.id).label("employee_count"),
                func.coalesce(func.sum(PayrollRunEmployee.gross_earnings), 0).label("gross_pay"),
                func.coalesce(
                    func.sum(
                        PayrollRunEmployee.total_employee_deductions
                        + PayrollRunEmployee.total_taxes
                    ),
                    0,
                ).label("deductions"),
                func.coalesce(func.sum(PayrollRunEmployee.employer_cost_base), 0).label("employer_cost"),
                func.coalesce(func.sum(PayrollRunEmployee.net_payable), 0).label("net_pay"),
            )
            .where(
                PayrollRunEmployee.company_id == company_id,
                PayrollRunEmployee.status_code == "included",
            )
            .group_by(PayrollRunEmployee.run_id)
            .subquery()
        )
        payment_totals_subquery = (
            select(
                PayrollRunEmployee.run_id.label("run_id"),
                func.coalesce(func.sum(PayrollPaymentRecord.amount_paid), 0).label("total_paid"),
            )
            .join(PayrollRunEmployee, PayrollRunEmployee.id == PayrollPaymentRecord.run_employee_id)
            .where(
                PayrollRunEmployee.company_id == company_id,
                PayrollRunEmployee.status_code == "included",
            )
            .group_by(PayrollRunEmployee.run_id)
            .subquery()
        )
        stmt = (
            select(
                PayrollRun.id.label("run_id"),
                PayrollRun.run_reference,
                PayrollRun.run_label,
                PayrollRun.period_year,
                PayrollRun.period_month,
                PayrollRun.run_date,
                PayrollRun.payment_date,
                PayrollRun.status_code,
                func.coalesce(employee_totals_subquery.c.employee_count, 0).label("employee_count"),
                func.coalesce(employee_totals_subquery.c.gross_pay, 0).label("gross_pay"),
                func.coalesce(employee_totals_subquery.c.deductions, 0).label("deductions"),
                func.coalesce(employee_totals_subquery.c.employer_cost, 0).label("employer_cost"),
                func.coalesce(employee_totals_subquery.c.net_pay, 0).label("net_pay"),
                func.coalesce(payment_totals_subquery.c.total_paid, 0).label("total_paid"),
                PayrollRun.posted_journal_entry_id.label("journal_entry_id"),
            )
            .outerjoin(employee_totals_subquery, employee_totals_subquery.c.run_id == PayrollRun.id)
            .outerjoin(payment_totals_subquery, payment_totals_subquery.c.run_id == PayrollRun.id)
            .where(
                PayrollRun.company_id == company_id,
                PayrollRun.status_code == "posted",
            )
        )
        if isinstance(run_id, int) and run_id > 0:
            stmt = stmt.where(PayrollRun.id == run_id)
        else:
            if date_from is not None:
                stmt = stmt.where(PayrollRun.run_date >= date_from)
            if date_to is not None:
                stmt = stmt.where(PayrollRun.run_date <= date_to)
        stmt = stmt.order_by(PayrollRun.run_date.desc(), PayrollRun.id.desc())

        rows: list[PayrollSummaryRunRow] = []
        for row in self._session.execute(stmt):
            net_pay = self._to_decimal(row.net_pay)
            total_paid = self._to_decimal(row.total_paid)
            rows.append(
                PayrollSummaryRunRow(
                    run_id=int(row.run_id),
                    run_reference=row.run_reference,
                    run_label=row.run_label,
                    period_year=int(row.period_year),
                    period_month=int(row.period_month),
                    run_date=row.run_date,
                    payment_date=row.payment_date,
                    status_code=row.status_code,
                    employee_count=int(row.employee_count or 0),
                    gross_pay=self._to_decimal(row.gross_pay),
                    deductions=self._to_decimal(row.deductions),
                    employer_cost=self._to_decimal(row.employer_cost),
                    net_pay=net_pay,
                    total_paid=total_paid,
                    outstanding_net_pay=(net_pay - total_paid).quantize(Decimal("0.01")),
                    journal_entry_id=row.journal_entry_id,
                )
            )
        return rows

    def list_employee_rows(
        self,
        company_id: int,
        run_ids: tuple[int, ...],
    ) -> list[PayrollSummaryEmployeeRow]:
        if not run_ids:
            return []

        if len(run_ids) == 1:
            stmt = (
                select(
                    Employee.id.label("employee_id"),
                    Employee.employee_number,
                    Employee.display_name,
                    PayrollRunEmployee.run_id,
                    PayrollRunEmployee.id.label("run_employee_id"),
                    PayrollRunEmployee.gross_earnings.label("gross_pay"),
                    (
                        PayrollRunEmployee.total_employee_deductions
                        + PayrollRunEmployee.total_taxes
                    ).label("deductions"),
                    PayrollRunEmployee.employer_cost_base.label("employer_cost"),
                    PayrollRunEmployee.net_payable.label("net_pay"),
                )
                .join(Employee, Employee.id == PayrollRunEmployee.employee_id)
                .where(
                    PayrollRunEmployee.company_id == company_id,
                    PayrollRunEmployee.run_id == run_ids[0],
                    PayrollRunEmployee.status_code == "included",
                )
                .order_by(Employee.employee_number.asc(), Employee.display_name.asc())
            )
            return [
                PayrollSummaryEmployeeRow(
                    employee_id=int(row.employee_id),
                    employee_number=row.employee_number,
                    employee_name=row.display_name,
                    run_id=int(row.run_id),
                    run_employee_id=int(row.run_employee_id),
                    gross_pay=self._to_decimal(row.gross_pay),
                    deductions=self._to_decimal(row.deductions),
                    employer_cost=self._to_decimal(row.employer_cost),
                    net_pay=self._to_decimal(row.net_pay),
                )
                for row in self._session.execute(stmt)
            ]

        stmt = (
            select(
                Employee.id.label("employee_id"),
                Employee.employee_number,
                Employee.display_name,
                func.coalesce(func.sum(PayrollRunEmployee.gross_earnings), 0).label("gross_pay"),
                func.coalesce(
                    func.sum(
                        PayrollRunEmployee.total_employee_deductions
                        + PayrollRunEmployee.total_taxes
                    ),
                    0,
                ).label("deductions"),
                func.coalesce(func.sum(PayrollRunEmployee.employer_cost_base), 0).label("employer_cost"),
                func.coalesce(func.sum(PayrollRunEmployee.net_payable), 0).label("net_pay"),
            )
            .join(Employee, Employee.id == PayrollRunEmployee.employee_id)
            .where(
                PayrollRunEmployee.company_id == company_id,
                PayrollRunEmployee.run_id.in_(run_ids),
                PayrollRunEmployee.status_code == "included",
            )
            .group_by(Employee.id, Employee.employee_number, Employee.display_name)
            .order_by(Employee.employee_number.asc(), Employee.display_name.asc())
        )
        return [
            PayrollSummaryEmployeeRow(
                employee_id=int(row.employee_id),
                employee_number=row.employee_number,
                employee_name=row.display_name,
                run_id=None,
                run_employee_id=None,
                gross_pay=self._to_decimal(row.gross_pay),
                deductions=self._to_decimal(row.deductions),
                employer_cost=self._to_decimal(row.employer_cost),
                net_pay=self._to_decimal(row.net_pay),
            )
            for row in self._session.execute(stmt)
        ]

    def list_statutory_rows(
        self,
        company_id: int,
        run_ids: tuple[int, ...],
    ) -> list[PayrollSummaryStatutoryRow]:
        if not run_ids:
            return []

        stmt = (
            select(
                PayrollRemittanceBatch.remittance_authority_code.label("authority_code"),
                func.coalesce(func.sum(PayrollRemittanceBatch.amount_due), 0).label("total_due"),
                func.coalesce(func.sum(PayrollRemittanceBatch.amount_paid), 0).label("total_remitted"),
                func.count(PayrollRemittanceBatch.id).label("batch_count"),
            )
            .where(
                PayrollRemittanceBatch.company_id == company_id,
                PayrollRemittanceBatch.payroll_run_id.in_(run_ids),
                PayrollRemittanceBatch.status_code != "cancelled",
            )
            .group_by(PayrollRemittanceBatch.remittance_authority_code)
            .order_by(PayrollRemittanceBatch.remittance_authority_code.asc())
        )
        return [
            PayrollSummaryStatutoryRow(
                authority_code=row.authority_code,
                total_due=self._to_decimal(row.total_due),
                total_remitted=self._to_decimal(row.total_remitted),
                batch_count=int(row.batch_count or 0),
            )
            for row in self._session.execute(stmt)
        ]

    @staticmethod
    def _to_decimal(value: object) -> Decimal:
        if isinstance(value, Decimal):
            return value.quantize(Decimal("0.01"))
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))
