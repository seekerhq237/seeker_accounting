from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.accounting.chart_of_accounts.models.account import Account
from seeker_accounting.modules.accounting.journals.models.journal_entry import JournalEntry
from seeker_accounting.modules.accounting.journals.models.journal_entry_line import JournalEntryLine
from seeker_accounting.modules.accounting.reference_data.models.account_type import AccountType
from seeker_accounting.modules.inventory.models.inventory_document import InventoryDocument
from seeker_accounting.modules.inventory.models.inventory_document_line import InventoryDocumentLine
from seeker_accounting.modules.payroll.models.payroll_run import PayrollRun
from seeker_accounting.modules.payroll.models.payroll_run_employee import PayrollRunEmployee
from seeker_accounting.modules.payroll.models.payroll_run_employee_project_allocation import (
    PayrollRunEmployeeProjectAllocation,
)
from seeker_accounting.modules.purchases.models.purchase_bill import PurchaseBill
from seeker_accounting.modules.purchases.models.purchase_bill_line import PurchaseBillLine
from seeker_accounting.modules.sales.models.sales_invoice import SalesInvoice
from seeker_accounting.modules.sales.models.sales_invoice_line import SalesInvoiceLine
from seeker_accounting.modules.treasury.models.treasury_transaction import TreasuryTransaction
from seeker_accounting.modules.treasury.models.treasury_transaction_line import TreasuryTransactionLine


@dataclass(frozen=True, slots=True)
class PeriodAmountRow:
    """A single year-month bucket with an aggregated amount."""

    period_year: int
    period_month: int
    amount: Decimal


class BudgetReportingRepository:
    """Read-only date-grouped queries for project trend series reporting.

    Queries span all actual-cost sources (purchase bills, treasury payments,
    inventory issues, payroll allocations, and manual journals) plus billed
    revenue (posted sales invoices). Each source is queried separately and
    combined by the caller to avoid cross-product joins.

    Date fields used per source:
      - purchase_bill  → PurchaseBill.bill_date
      - treasury       → TreasuryTransaction.transaction_date
      - inventory      → InventoryDocument.document_date
      - payroll        → PayrollRun.run_date
      - manual_journal → JournalEntry.entry_date
      - sales_invoice  → SalesInvoice.invoice_date
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_actual_cost_by_period(
        self,
        company_id: int,
        project_id: int,
    ) -> list[PeriodAmountRow]:
        """Return monthly actual cost aggregated across all 5 cost sources."""
        bucket: dict[tuple[int, int], Decimal] = {}
        for rows in (
            self._purchase_bill_costs_by_period(company_id, project_id),
            self._treasury_payment_costs_by_period(company_id, project_id),
            self._inventory_issue_costs_by_period(company_id, project_id),
            self._payroll_allocation_costs_by_period(company_id, project_id),
            self._manual_journal_costs_by_period(company_id, project_id),
        ):
            for row in rows:
                key = (row.period_year, row.period_month)
                bucket[key] = bucket.get(key, Decimal("0.00")) + row.amount
        return sorted(
            [
                PeriodAmountRow(period_year=y, period_month=m, amount=amt)
                for (y, m), amt in bucket.items()
            ],
            key=lambda r: (r.period_year, r.period_month),
        )

    def list_revenue_by_period(
        self,
        company_id: int,
        project_id: int,
    ) -> list[PeriodAmountRow]:
        """Return monthly billed revenue from posted sales invoices."""
        resolved_project_id = func.coalesce(SalesInvoiceLine.project_id, SalesInvoice.project_id)
        statement = (
            select(
                extract("year", SalesInvoice.invoice_date).label("period_year"),
                extract("month", SalesInvoice.invoice_date).label("period_month"),
                func.coalesce(func.sum(SalesInvoiceLine.line_subtotal_amount), 0).label("amount"),
            )
            .join(SalesInvoice, SalesInvoice.id == SalesInvoiceLine.sales_invoice_id)
            .where(
                SalesInvoice.company_id == company_id,
                SalesInvoice.status_code == "posted",
                SalesInvoice.posted_at.is_not(None),
                resolved_project_id == project_id,
            )
            .group_by(
                extract("year", SalesInvoice.invoice_date),
                extract("month", SalesInvoice.invoice_date),
            )
        )
        return self._build_period_rows(statement)

    # ------------------------------------------------------------------
    # Private per-source queries
    # ------------------------------------------------------------------

    def _purchase_bill_costs_by_period(
        self, company_id: int, project_id: int
    ) -> list[PeriodAmountRow]:
        resolved_project_id = func.coalesce(PurchaseBillLine.project_id, PurchaseBill.project_id)
        statement = (
            select(
                extract("year", PurchaseBill.bill_date).label("period_year"),
                extract("month", PurchaseBill.bill_date).label("period_month"),
                func.coalesce(func.sum(PurchaseBillLine.line_subtotal_amount), 0).label("amount"),
            )
            .join(PurchaseBill, PurchaseBill.id == PurchaseBillLine.purchase_bill_id)
            .where(
                PurchaseBill.company_id == company_id,
                PurchaseBill.status_code == "posted",
                PurchaseBill.posted_at.is_not(None),
                resolved_project_id == project_id,
            )
            .group_by(
                extract("year", PurchaseBill.bill_date),
                extract("month", PurchaseBill.bill_date),
            )
        )
        return self._build_period_rows(statement)

    def _treasury_payment_costs_by_period(
        self, company_id: int, project_id: int
    ) -> list[PeriodAmountRow]:
        resolved_project_id = func.coalesce(
            TreasuryTransactionLine.project_id, TreasuryTransaction.project_id
        )
        statement = (
            select(
                extract("year", TreasuryTransaction.transaction_date).label("period_year"),
                extract("month", TreasuryTransaction.transaction_date).label("period_month"),
                func.coalesce(func.sum(TreasuryTransactionLine.amount), 0).label("amount"),
            )
            .join(
                TreasuryTransaction,
                TreasuryTransaction.id == TreasuryTransactionLine.treasury_transaction_id,
            )
            .where(
                TreasuryTransaction.company_id == company_id,
                TreasuryTransaction.status_code == "posted",
                TreasuryTransaction.posted_at.is_not(None),
                TreasuryTransaction.transaction_type_code.in_(("cash_payment", "bank_payment")),
                resolved_project_id == project_id,
            )
            .group_by(
                extract("year", TreasuryTransaction.transaction_date),
                extract("month", TreasuryTransaction.transaction_date),
            )
        )
        return self._build_period_rows(statement)

    def _inventory_issue_costs_by_period(
        self, company_id: int, project_id: int
    ) -> list[PeriodAmountRow]:
        resolved_project_id = func.coalesce(
            InventoryDocumentLine.project_id, InventoryDocument.project_id
        )
        statement = (
            select(
                extract("year", InventoryDocument.document_date).label("period_year"),
                extract("month", InventoryDocument.document_date).label("period_month"),
                func.coalesce(func.sum(InventoryDocumentLine.line_amount), 0).label("amount"),
            )
            .join(
                InventoryDocument,
                InventoryDocument.id == InventoryDocumentLine.inventory_document_id,
            )
            .where(
                InventoryDocument.company_id == company_id,
                InventoryDocument.status_code == "posted",
                InventoryDocument.posted_at.is_not(None),
                InventoryDocument.document_type_code == "issue",
                resolved_project_id == project_id,
            )
            .group_by(
                extract("year", InventoryDocument.document_date),
                extract("month", InventoryDocument.document_date),
            )
        )
        return self._build_period_rows(statement)

    def _payroll_allocation_costs_by_period(
        self, company_id: int, project_id: int
    ) -> list[PeriodAmountRow]:
        statement = (
            select(
                extract("year", PayrollRun.run_date).label("period_year"),
                extract("month", PayrollRun.run_date).label("period_month"),
                func.coalesce(
                    func.sum(PayrollRunEmployeeProjectAllocation.allocated_cost_amount),
                    0,
                ).label("amount"),
            )
            .join(
                PayrollRunEmployee,
                PayrollRunEmployee.id
                == PayrollRunEmployeeProjectAllocation.payroll_run_employee_id,
            )
            .join(PayrollRun, PayrollRun.id == PayrollRunEmployee.run_id)
            .where(
                PayrollRun.company_id == company_id,
                PayrollRunEmployeeProjectAllocation.project_id == project_id,
                PayrollRun.status_code.in_(("approved", "posted")),
                PayrollRunEmployee.status_code == "included",
            )
            .group_by(
                extract("year", PayrollRun.run_date),
                extract("month", PayrollRun.run_date),
            )
        )
        return self._build_period_rows(statement)

    def _manual_journal_costs_by_period(
        self, company_id: int, project_id: int
    ) -> list[PeriodAmountRow]:
        """Manual journals: source_module_code IS NULL, project dimension on the line.

        Uses net debit (debit - credit) on EXPENSE-type accounts as cost.
        """
        statement = (
            select(
                extract("year", JournalEntry.entry_date).label("period_year"),
                extract("month", JournalEntry.entry_date).label("period_month"),
                func.coalesce(
                    func.sum(JournalEntryLine.debit_amount - JournalEntryLine.credit_amount),
                    0,
                ).label("amount"),
            )
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
            .join(Account, Account.id == JournalEntryLine.account_id)
            .join(AccountType, AccountType.id == Account.account_type_id)
            .where(
                JournalEntry.company_id == company_id,
                JournalEntry.status_code == "POSTED",
                JournalEntry.source_module_code.is_(None),
                JournalEntryLine.project_id == project_id,
                AccountType.financial_statement_section_code == "EXPENSE",
            )
            .group_by(
                extract("year", JournalEntry.entry_date),
                extract("month", JournalEntry.entry_date),
            )
        )
        return self._build_period_rows(statement)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_period_rows(self, statement) -> list[PeriodAmountRow]:
        result: list[PeriodAmountRow] = []
        for row in self._session.execute(statement):
            amount = self._to_decimal(row.amount)
            if amount == Decimal("0.00"):
                continue
            result.append(
                PeriodAmountRow(
                    period_year=int(row.period_year),
                    period_month=int(row.period_month),
                    amount=amount,
                )
            )
        return result

    @staticmethod
    def _to_decimal(value: object) -> Decimal:
        if isinstance(value, Decimal):
            return value.quantize(Decimal("0.01"))
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))
