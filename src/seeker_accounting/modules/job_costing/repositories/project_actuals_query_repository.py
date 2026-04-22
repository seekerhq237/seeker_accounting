from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.accounting.chart_of_accounts.models.account import Account
from seeker_accounting.modules.accounting.journals.models.journal_entry import JournalEntry
from seeker_accounting.modules.accounting.journals.models.journal_entry_line import JournalEntryLine
from seeker_accounting.modules.accounting.reference_data.models.account_type import AccountType
from seeker_accounting.modules.contracts_projects.models.project_cost_code import ProjectCostCode
from seeker_accounting.modules.contracts_projects.models.project_job import ProjectJob
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
class ProjectDimensionAmountRow:
    project_job_id: int | None
    project_job_code: str | None
    project_job_name: str | None
    project_cost_code_id: int | None
    project_cost_code: str | None
    project_cost_code_name: str | None
    amount: Decimal


@dataclass(frozen=True, slots=True)
class ProjectActualCostBreakdownRow(ProjectDimensionAmountRow):
    source_type_code: str
    source_type_label: str


class ProjectActualsQueryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_actual_cost_breakdown(
        self,
        company_id: int,
        project_id: int,
    ) -> list[ProjectActualCostBreakdownRow]:
        rows: list[ProjectActualCostBreakdownRow] = []
        rows.extend(self._list_purchase_bill_costs(company_id, project_id))
        rows.extend(self._list_treasury_payment_costs(company_id, project_id))
        rows.extend(self._list_inventory_issue_costs(company_id, project_id))
        rows.extend(self._list_payroll_allocation_costs(company_id, project_id))
        rows.extend(self._list_manual_journal_costs(company_id, project_id))
        return sorted(
            rows,
            key=lambda row: (
                row.source_type_label,
                row.project_job_code or "",
                row.project_cost_code or "",
            ),
        )

    def list_actual_cost_by_dimension(
        self,
        company_id: int,
        project_id: int,
    ) -> list[ProjectDimensionAmountRow]:
        aggregated: dict[
            tuple[int | None, str | None, str | None, int | None, str | None, str | None],
            Decimal,
        ] = {}
        for row in self.list_actual_cost_breakdown(company_id, project_id):
            key = (
                row.project_job_id,
                row.project_job_code,
                row.project_job_name,
                row.project_cost_code_id,
                row.project_cost_code,
                row.project_cost_code_name,
            )
            aggregated[key] = aggregated.get(key, Decimal("0.00")) + row.amount

        result = [
            ProjectDimensionAmountRow(
                project_job_id=key[0],
                project_job_code=key[1],
                project_job_name=key[2],
                project_cost_code_id=key[3],
                project_cost_code=key[4],
                project_cost_code_name=key[5],
                amount=amount,
            )
            for key, amount in aggregated.items()
        ]
        return sorted(
            result,
            key=lambda row: (
                row.project_job_code or "",
                row.project_cost_code or "",
            ),
        )

    def _list_purchase_bill_costs(
        self,
        company_id: int,
        project_id: int,
    ) -> list[ProjectActualCostBreakdownRow]:
        resolved_project_id = func.coalesce(PurchaseBillLine.project_id, PurchaseBill.project_id)
        statement = (
            select(
                PurchaseBillLine.project_job_id.label("project_job_id"),
                ProjectJob.job_code.label("project_job_code"),
                ProjectJob.job_name.label("project_job_name"),
                PurchaseBillLine.project_cost_code_id.label("project_cost_code_id"),
                ProjectCostCode.code.label("project_cost_code"),
                ProjectCostCode.name.label("project_cost_code_name"),
                func.coalesce(func.sum(PurchaseBillLine.line_subtotal_amount), 0).label("amount"),
            )
            .join(PurchaseBill, PurchaseBill.id == PurchaseBillLine.purchase_bill_id)
            .outerjoin(ProjectJob, ProjectJob.id == PurchaseBillLine.project_job_id)
            .outerjoin(ProjectCostCode, ProjectCostCode.id == PurchaseBillLine.project_cost_code_id)
            .where(
                PurchaseBill.company_id == company_id,
                PurchaseBill.status_code == "posted",
                PurchaseBill.posted_at.is_not(None),
                resolved_project_id == project_id,
            )
            .group_by(
                PurchaseBillLine.project_job_id,
                ProjectJob.job_code,
                ProjectJob.job_name,
                PurchaseBillLine.project_cost_code_id,
                ProjectCostCode.code,
                ProjectCostCode.name,
            )
        )
        return self._build_breakdown_rows(statement, "purchase_bill", "Purchase Bills")

    def _list_treasury_payment_costs(
        self,
        company_id: int,
        project_id: int,
    ) -> list[ProjectActualCostBreakdownRow]:
        resolved_project_id = func.coalesce(TreasuryTransactionLine.project_id, TreasuryTransaction.project_id)
        statement = (
            select(
                TreasuryTransactionLine.project_job_id.label("project_job_id"),
                ProjectJob.job_code.label("project_job_code"),
                ProjectJob.job_name.label("project_job_name"),
                TreasuryTransactionLine.project_cost_code_id.label("project_cost_code_id"),
                ProjectCostCode.code.label("project_cost_code"),
                ProjectCostCode.name.label("project_cost_code_name"),
                func.coalesce(func.sum(TreasuryTransactionLine.amount), 0).label("amount"),
            )
            .join(TreasuryTransaction, TreasuryTransaction.id == TreasuryTransactionLine.treasury_transaction_id)
            .outerjoin(ProjectJob, ProjectJob.id == TreasuryTransactionLine.project_job_id)
            .outerjoin(ProjectCostCode, ProjectCostCode.id == TreasuryTransactionLine.project_cost_code_id)
            .where(
                TreasuryTransaction.company_id == company_id,
                TreasuryTransaction.status_code == "posted",
                TreasuryTransaction.posted_at.is_not(None),
                TreasuryTransaction.transaction_type_code.in_(("cash_payment", "bank_payment")),
                resolved_project_id == project_id,
            )
            .group_by(
                TreasuryTransactionLine.project_job_id,
                ProjectJob.job_code,
                ProjectJob.job_name,
                TreasuryTransactionLine.project_cost_code_id,
                ProjectCostCode.code,
                ProjectCostCode.name,
            )
        )
        return self._build_breakdown_rows(statement, "treasury_payment", "Treasury Payments")

    def _list_inventory_issue_costs(
        self,
        company_id: int,
        project_id: int,
    ) -> list[ProjectActualCostBreakdownRow]:
        resolved_project_id = func.coalesce(InventoryDocumentLine.project_id, InventoryDocument.project_id)
        statement = (
            select(
                InventoryDocumentLine.project_job_id.label("project_job_id"),
                ProjectJob.job_code.label("project_job_code"),
                ProjectJob.job_name.label("project_job_name"),
                InventoryDocumentLine.project_cost_code_id.label("project_cost_code_id"),
                ProjectCostCode.code.label("project_cost_code"),
                ProjectCostCode.name.label("project_cost_code_name"),
                func.coalesce(func.sum(InventoryDocumentLine.line_amount), 0).label("amount"),
            )
            .join(InventoryDocument, InventoryDocument.id == InventoryDocumentLine.inventory_document_id)
            .outerjoin(ProjectJob, ProjectJob.id == InventoryDocumentLine.project_job_id)
            .outerjoin(ProjectCostCode, ProjectCostCode.id == InventoryDocumentLine.project_cost_code_id)
            .where(
                InventoryDocument.company_id == company_id,
                InventoryDocument.status_code == "posted",
                InventoryDocument.posted_at.is_not(None),
                InventoryDocument.document_type_code == "issue",
                resolved_project_id == project_id,
            )
            .group_by(
                InventoryDocumentLine.project_job_id,
                ProjectJob.job_code,
                ProjectJob.job_name,
                InventoryDocumentLine.project_cost_code_id,
                ProjectCostCode.code,
                ProjectCostCode.name,
            )
        )
        return self._build_breakdown_rows(statement, "inventory_issue", "Inventory Issues")

    def _list_payroll_allocation_costs(
        self,
        company_id: int,
        project_id: int,
    ) -> list[ProjectActualCostBreakdownRow]:
        statement = (
            select(
                PayrollRunEmployeeProjectAllocation.project_job_id.label("project_job_id"),
                ProjectJob.job_code.label("project_job_code"),
                ProjectJob.job_name.label("project_job_name"),
                PayrollRunEmployeeProjectAllocation.project_cost_code_id.label("project_cost_code_id"),
                ProjectCostCode.code.label("project_cost_code"),
                ProjectCostCode.name.label("project_cost_code_name"),
                func.coalesce(
                    func.sum(PayrollRunEmployeeProjectAllocation.allocated_cost_amount),
                    0,
                ).label("amount"),
            )
            .join(
                PayrollRunEmployee,
                PayrollRunEmployee.id == PayrollRunEmployeeProjectAllocation.payroll_run_employee_id,
            )
            .join(PayrollRun, PayrollRun.id == PayrollRunEmployee.run_id)
            .outerjoin(ProjectJob, ProjectJob.id == PayrollRunEmployeeProjectAllocation.project_job_id)
            .outerjoin(ProjectCostCode, ProjectCostCode.id == PayrollRunEmployeeProjectAllocation.project_cost_code_id)
            .where(
                PayrollRun.company_id == company_id,
                PayrollRunEmployeeProjectAllocation.project_id == project_id,
                PayrollRun.status_code.in_(("approved", "posted")),
                PayrollRunEmployee.status_code == "included",
            )
            .group_by(
                PayrollRunEmployeeProjectAllocation.project_job_id,
                ProjectJob.job_code,
                ProjectJob.job_name,
                PayrollRunEmployeeProjectAllocation.project_cost_code_id,
                ProjectCostCode.code,
                ProjectCostCode.name,
            )
        )
        return self._build_breakdown_rows(statement, "payroll_allocation", "Payroll Allocations")

    def _list_manual_journal_costs(
        self,
        company_id: int,
        project_id: int,
    ) -> list[ProjectActualCostBreakdownRow]:
        net_amount = func.sum(JournalEntryLine.debit_amount - JournalEntryLine.credit_amount)
        statement = (
            select(
                JournalEntryLine.project_job_id.label("project_job_id"),
                ProjectJob.job_code.label("project_job_code"),
                ProjectJob.job_name.label("project_job_name"),
                JournalEntryLine.project_cost_code_id.label("project_cost_code_id"),
                ProjectCostCode.code.label("project_cost_code"),
                ProjectCostCode.name.label("project_cost_code_name"),
                func.coalesce(net_amount, 0).label("amount"),
            )
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
            .join(Account, Account.id == JournalEntryLine.account_id)
            .join(AccountType, AccountType.id == Account.account_type_id)
            .outerjoin(ProjectJob, ProjectJob.id == JournalEntryLine.project_job_id)
            .outerjoin(ProjectCostCode, ProjectCostCode.id == JournalEntryLine.project_cost_code_id)
            .where(
                JournalEntry.company_id == company_id,
                JournalEntry.status_code == "POSTED",
                JournalEntry.posted_at.is_not(None),
                JournalEntry.source_module_code.is_(None),
                JournalEntryLine.project_id == project_id,
                AccountType.financial_statement_section_code == "EXPENSE",
            )
            .group_by(
                JournalEntryLine.project_job_id,
                ProjectJob.job_code,
                ProjectJob.job_name,
                JournalEntryLine.project_cost_code_id,
                ProjectCostCode.code,
                ProjectCostCode.name,
            )
        )
        return self._build_breakdown_rows(statement, "manual_journal", "Manual Journals")

    def _build_breakdown_rows(
        self,
        statement,
        source_type_code: str,
        source_type_label: str,
    ) -> list[ProjectActualCostBreakdownRow]:
        result: list[ProjectActualCostBreakdownRow] = []
        for row in self._session.execute(statement):
            amount = self._to_decimal(row.amount)
            if amount == Decimal("0.00"):
                continue
            result.append(
                ProjectActualCostBreakdownRow(
                    source_type_code=source_type_code,
                    source_type_label=source_type_label,
                    project_job_id=row.project_job_id,
                    project_job_code=row.project_job_code,
                    project_job_name=row.project_job_name,
                    project_cost_code_id=row.project_cost_code_id,
                    project_cost_code=row.project_cost_code,
                    project_cost_code_name=row.project_cost_code_name,
                    amount=amount,
                )
            )
        return result

    @staticmethod
    def _to_decimal(value: object) -> Decimal:
        if isinstance(value, Decimal):
            return value.quantize(Decimal("0.01"))
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))