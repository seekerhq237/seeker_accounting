from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.purchases.models.purchase_bill import PurchaseBill
from seeker_accounting.modules.sales.models.sales_invoice import SalesInvoice


@dataclass(frozen=True, slots=True)
class OperationalPeriodTotalRow:
    period_year: int
    period_month: int
    total_amount: Decimal


class FinancialAnalysisRepository:
    """Focused operational totals used by 14H ratio and cycle analysis."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def sum_posted_sales_invoices(
        self,
        company_id: int,
        date_from: date | None,
        date_to: date | None,
    ) -> Decimal:
        stmt = select(func.coalesce(func.sum(SalesInvoice.total_amount), 0)).where(
            *self._sales_conditions(company_id, date_from, date_to)
        )
        return self._to_amount(self._session.scalar(stmt))

    def sum_posted_purchase_bills(
        self,
        company_id: int,
        date_from: date | None,
        date_to: date | None,
    ) -> Decimal:
        stmt = select(func.coalesce(func.sum(PurchaseBill.total_amount), 0)).where(
            *self._purchase_conditions(company_id, date_from, date_to)
        )
        return self._to_amount(self._session.scalar(stmt))

    def list_monthly_sales_invoice_totals(
        self,
        company_id: int,
        date_from: date | None,
        date_to: date | None,
    ) -> list[OperationalPeriodTotalRow]:
        stmt = (
            select(
                extract("year", SalesInvoice.invoice_date).label("period_year"),
                extract("month", SalesInvoice.invoice_date).label("period_month"),
                func.coalesce(func.sum(SalesInvoice.total_amount), 0).label("total_amount"),
            )
            .where(*self._sales_conditions(company_id, date_from, date_to))
            .group_by(
                extract("year", SalesInvoice.invoice_date),
                extract("month", SalesInvoice.invoice_date),
            )
            .order_by(
                extract("year", SalesInvoice.invoice_date).asc(),
                extract("month", SalesInvoice.invoice_date).asc(),
            )
        )
        rows: list[OperationalPeriodTotalRow] = []
        for row in self._session.execute(stmt):
            rows.append(
                OperationalPeriodTotalRow(
                    period_year=int(row.period_year),
                    period_month=int(row.period_month),
                    total_amount=self._to_amount(row.total_amount),
                )
            )
        return rows

    def list_monthly_purchase_bill_totals(
        self,
        company_id: int,
        date_from: date | None,
        date_to: date | None,
    ) -> list[OperationalPeriodTotalRow]:
        stmt = (
            select(
                extract("year", PurchaseBill.bill_date).label("period_year"),
                extract("month", PurchaseBill.bill_date).label("period_month"),
                func.coalesce(func.sum(PurchaseBill.total_amount), 0).label("total_amount"),
            )
            .where(*self._purchase_conditions(company_id, date_from, date_to))
            .group_by(
                extract("year", PurchaseBill.bill_date),
                extract("month", PurchaseBill.bill_date),
            )
            .order_by(
                extract("year", PurchaseBill.bill_date).asc(),
                extract("month", PurchaseBill.bill_date).asc(),
            )
        )
        rows: list[OperationalPeriodTotalRow] = []
        for row in self._session.execute(stmt):
            rows.append(
                OperationalPeriodTotalRow(
                    period_year=int(row.period_year),
                    period_month=int(row.period_month),
                    total_amount=self._to_amount(row.total_amount),
                )
            )
        return rows

    @staticmethod
    def _sales_conditions(
        company_id: int,
        date_from: date | None,
        date_to: date | None,
    ) -> list[object]:
        conditions: list[object] = [
            SalesInvoice.company_id == company_id,
            SalesInvoice.status_code == "posted",
        ]
        if date_from is not None:
            conditions.append(SalesInvoice.invoice_date >= date_from)
        if date_to is not None:
            conditions.append(SalesInvoice.invoice_date <= date_to)
        return conditions

    @staticmethod
    def _purchase_conditions(
        company_id: int,
        date_from: date | None,
        date_to: date | None,
    ) -> list[object]:
        conditions: list[object] = [
            PurchaseBill.company_id == company_id,
            PurchaseBill.status_code == "posted",
        ]
        if date_from is not None:
            conditions.append(PurchaseBill.bill_date >= date_from)
        if date_to is not None:
            conditions.append(PurchaseBill.bill_date <= date_to)
        return conditions

    @staticmethod
    def _to_amount(value: object) -> Decimal:
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))
