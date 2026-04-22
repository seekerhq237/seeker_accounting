from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.payroll.models.payroll_payment_record import PayrollPaymentRecord
from seeker_accounting.modules.payroll.models.payroll_remittance_batch import PayrollRemittanceBatch
from seeker_accounting.modules.payroll.models.payroll_run import PayrollRun
from seeker_accounting.modules.payroll.models.payroll_run_employee import PayrollRunEmployee


class PayrollSummaryRepository:
    """Query-only repository for payroll summary and exposure views.

    Does not own any write operations.  All results are raw scalar queries
    assembled by PayrollSummaryService into DTOs.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_run_employee_totals(
        self, company_id: int, run_id: int
    ) -> dict[str, Decimal]:
        """Aggregate the six bases and summary totals across included employees."""
        stmt = (
            select(
                func.sum(PayrollRunEmployee.gross_earnings).label("gross_earnings"),
                func.sum(PayrollRunEmployee.net_payable).label("net_payable"),
                func.sum(PayrollRunEmployee.total_taxes).label("taxes"),
                func.sum(PayrollRunEmployee.total_employee_deductions).label("deductions"),
                func.sum(PayrollRunEmployee.total_employer_contributions).label(
                    "employer_contributions"
                ),
                func.sum(PayrollRunEmployee.employer_cost_base).label("employer_cost"),
                func.count(PayrollRunEmployee.id).label("included_count"),
            )
            .where(
                PayrollRunEmployee.company_id == company_id,
                PayrollRunEmployee.run_id == run_id,
                PayrollRunEmployee.status_code == "included",
            )
        )
        row = self._session.execute(stmt).one()
        return {
            "gross_earnings": Decimal(str(row.gross_earnings or 0)),
            "net_payable": Decimal(str(row.net_payable or 0)),
            "taxes": Decimal(str(row.taxes or 0)),
            "deductions": Decimal(str(row.deductions or 0)),
            "employer_contributions": Decimal(str(row.employer_contributions or 0)),
            "employer_cost": Decimal(str(row.employer_cost or 0)),
            "included_count": int(row.included_count or 0),
        }

    def get_error_count(self, company_id: int, run_id: int) -> int:
        stmt = select(func.count(PayrollRunEmployee.id)).where(
            PayrollRunEmployee.company_id == company_id,
            PayrollRunEmployee.run_id == run_id,
            PayrollRunEmployee.status_code == "error",
        )
        return int(self._session.scalar(stmt) or 0)

    def get_payment_status_counts(
        self, company_id: int, run_id: int
    ) -> dict[str, int]:
        """Return counts for paid/partial/unpaid among included employees."""
        stmt = (
            select(
                PayrollRunEmployee.payment_status_code,
                func.count(PayrollRunEmployee.id).label("cnt"),
            )
            .where(
                PayrollRunEmployee.company_id == company_id,
                PayrollRunEmployee.run_id == run_id,
                PayrollRunEmployee.status_code == "included",
            )
            .group_by(PayrollRunEmployee.payment_status_code)
        )
        counts = {"paid": 0, "partial": 0, "unpaid": 0}
        for row in self._session.execute(stmt).all():
            if row.payment_status_code in counts:
                counts[row.payment_status_code] = int(row.cnt)
        return counts

    def get_net_pay_exposure(
        self, company_id: int, run_id: int
    ) -> dict[str, Decimal]:
        """Total net payable vs total paid for a run's included employees."""
        stmt = (
            select(
                func.sum(PayrollRunEmployee.net_payable).label("total_net"),
            )
            .where(
                PayrollRunEmployee.company_id == company_id,
                PayrollRunEmployee.run_id == run_id,
                PayrollRunEmployee.status_code == "included",
            )
        )
        net_row = self._session.execute(stmt).one()
        total_net = Decimal(str(net_row.total_net or 0))

        # Sum payments across all employees in this run
        from seeker_accounting.modules.payroll.models.payroll_run_employee import (
            PayrollRunEmployee as PRE,
        )

        pay_stmt = (
            select(func.sum(PayrollPaymentRecord.amount_paid).label("total_paid"))
            .join(PRE, PayrollPaymentRecord.run_employee_id == PRE.id)
            .where(
                PayrollPaymentRecord.company_id == company_id,
                PRE.run_id == run_id,
                PRE.status_code == "included",
            )
        )
        pay_row = self._session.execute(pay_stmt).one()
        total_paid = Decimal(str(pay_row.total_paid or 0))
        return {
            "total_net": total_net,
            "total_paid": total_paid,
            "outstanding": total_net - total_paid,
        }

    def get_remittance_exposure_by_authority(
        self, company_id: int, run_id: int | None = None
    ) -> list[dict]:
        """Aggregate remittance batch totals grouped by authority."""
        stmt = (
            select(
                PayrollRemittanceBatch.remittance_authority_code,
                func.sum(PayrollRemittanceBatch.amount_due).label("total_due"),
                func.sum(PayrollRemittanceBatch.amount_paid).label("total_paid"),
                func.count(PayrollRemittanceBatch.id).label("batch_count"),
            )
            .where(
                PayrollRemittanceBatch.company_id == company_id,
                PayrollRemittanceBatch.status_code.notin_(["cancelled"]),
            )
            .group_by(PayrollRemittanceBatch.remittance_authority_code)
        )
        if run_id is not None:
            stmt = stmt.where(PayrollRemittanceBatch.payroll_run_id == run_id)
        rows = self._session.execute(stmt).all()
        return [
            {
                "authority": row.remittance_authority_code,
                "total_due": Decimal(str(row.total_due or 0)),
                "total_paid": Decimal(str(row.total_paid or 0)),
                "batch_count": int(row.batch_count),
            }
            for row in rows
        ]
