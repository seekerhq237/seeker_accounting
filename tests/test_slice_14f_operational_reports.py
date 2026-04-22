from __future__ import annotations

import unittest
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from seeker_accounting.modules.reporting.dto.operational_report_filter_dto import (
    OperationalReportFilterDTO,
)
from seeker_accounting.modules.reporting.repositories.ap_aging_report_repository import (
    APAgingDocumentRow,
)
from seeker_accounting.modules.reporting.repositories.ar_aging_report_repository import (
    ARAgingDocumentRow,
)
from seeker_accounting.modules.reporting.repositories.customer_statement_repository import (
    CustomerStatementMovementRow,
)
from seeker_accounting.modules.reporting.repositories.payroll_summary_report_repository import (
    PayrollSummaryEmployeeRow,
    PayrollSummaryRunRow,
    PayrollSummaryStatutoryRow,
)
from seeker_accounting.modules.reporting.repositories.treasury_report_repository import (
    TreasuryMovementSourceRow,
)
from seeker_accounting.modules.reporting.services.ap_aging_report_service import (
    APAgingReportService,
)
from seeker_accounting.modules.reporting.services.ar_aging_report_service import (
    ARAgingReportService,
)
from seeker_accounting.modules.reporting.services.customer_statement_service import (
    CustomerStatementService,
)
from seeker_accounting.modules.reporting.services.payroll_summary_report_service import (
    PayrollSummaryReportService,
)
from seeker_accounting.modules.reporting.services.reporting_workspace_service import (
    ReportingWorkspaceService,
)
from seeker_accounting.modules.reporting.services.treasury_report_service import (
    TreasuryReportService,
)


class _FakeUnitOfWork:
    def __init__(self) -> None:
        self.session = object()

    def __enter__(self) -> _FakeUnitOfWork:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        return None


def _fake_uow_factory() -> _FakeUnitOfWork:
    return _FakeUnitOfWork()


@dataclass
class _FakeARAgingRepository:
    rows: list[ARAgingDocumentRow]
    control_balance: Decimal | None

    def list_open_documents(self, company_id: int, as_of_date: date) -> list[ARAgingDocumentRow]:  # noqa: ARG002
        return list(self.rows)

    def sum_control_balance(self, company_id: int, as_of_date: date) -> Decimal | None:  # noqa: ARG002
        return self.control_balance

    def get_customer_identity(self, company_id: int, customer_id: int) -> tuple[str, str] | None:  # noqa: ARG002
        for row in self.rows:
            if row.customer_id == customer_id:
                return row.customer_code, row.customer_name
        return None


@dataclass
class _FakeAPAgingRepository:
    rows: list[APAgingDocumentRow]
    control_balance: Decimal | None

    def list_open_documents(self, company_id: int, as_of_date: date) -> list[APAgingDocumentRow]:  # noqa: ARG002
        return list(self.rows)

    def sum_control_balance(self, company_id: int, as_of_date: date) -> Decimal | None:  # noqa: ARG002
        return self.control_balance

    def get_supplier_identity(self, company_id: int, supplier_id: int) -> tuple[str, str] | None:  # noqa: ARG002
        for row in self.rows:
            if row.supplier_id == supplier_id:
                return row.supplier_code, row.supplier_name
        return None


@dataclass
class _FakeCustomerStatementRepository:
    identity: tuple[str, str]
    opening_balance: Decimal
    movements: list[CustomerStatementMovementRow]

    def get_customer_identity(self, company_id: int, customer_id: int) -> tuple[str, str] | None:  # noqa: ARG002
        return self.identity

    def sum_opening_balance(self, company_id: int, customer_id: int, date_from: date | None) -> Decimal:  # noqa: ARG002
        return self.opening_balance

    def list_period_movements(
        self,
        company_id: int,
        customer_id: int,
        date_from: date | None,
        date_to: date | None,
    ) -> list[CustomerStatementMovementRow]:  # noqa: ARG002
        return list(self.movements)


@dataclass
class _FakePayrollSummaryRepository:
    run_rows: list[PayrollSummaryRunRow]
    employee_rows: list[PayrollSummaryEmployeeRow]
    statutory_rows: list[PayrollSummaryStatutoryRow]

    def list_run_rows(
        self,
        company_id: int,
        date_from: date | None,
        date_to: date | None,
        run_id: int | None = None,
    ) -> list[PayrollSummaryRunRow]:  # noqa: ARG002
        if run_id is None:
            return list(self.run_rows)
        return [row for row in self.run_rows if row.run_id == run_id]

    def list_employee_rows(self, company_id: int, run_ids: tuple[int, ...]) -> list[PayrollSummaryEmployeeRow]:  # noqa: ARG002
        return [row for row in self.employee_rows if row.run_id in run_ids or row.run_id is None]

    def list_statutory_rows(self, company_id: int, run_ids: tuple[int, ...]) -> list[PayrollSummaryStatutoryRow]:  # noqa: ARG002
        return list(self.statutory_rows) if run_ids else []


@dataclass
class _FakeTreasuryReportRepository:
    opening_rows: list[TreasuryMovementSourceRow]
    period_rows: list[TreasuryMovementSourceRow]

    def list_movement_rows(
        self,
        company_id: int,
        date_from: date | None,
        date_to: date | None,
        financial_account_id: int | None = None,
    ) -> list[TreasuryMovementSourceRow]:  # noqa: ARG002
        rows = self.opening_rows if date_from is None else self.period_rows
        if financial_account_id is None:
            return list(rows)
        return [row for row in rows if row.financial_account_id == financial_account_id]


class ReportingWorkspaceServiceTests(unittest.TestCase):
    def test_operational_reports_tab_uses_slice_14f_tiles(self) -> None:
        workspace = ReportingWorkspaceService().get_workspace_dto()
        operational_tab = next(tab for tab in workspace.tabs if tab.tab_key == "operational_reports")

        self.assertTrue(operational_tab.is_launcher)
        self.assertEqual(
            [tile.tile_key for tile in operational_tab.tiles],
            [
                "ar_aging",
                "ap_aging",
                "customer_statements",
                "supplier_statements",
                "payroll_summary",
                "treasury_reports",
            ],
        )


class AgingReportServiceTests(unittest.TestCase):
    def test_ar_aging_buckets_overdue_and_warns_on_control_delta(self) -> None:
        repo = _FakeARAgingRepository(
            rows=[
                ARAgingDocumentRow(
                    customer_id=1,
                    customer_code="CUST-001",
                    customer_name="Acme Customer",
                    document_kind="invoice",
                    document_number="INV-001",
                    document_date=date(2026, 1, 10),
                    due_date=date(2026, 1, 31),
                    reference_text="PO-1",
                    description="Invoice",
                    open_amount=Decimal("100.00"),
                    journal_entry_id=11,
                    source_document_type="sales_invoice",
                    source_document_id=101,
                ),
                ARAgingDocumentRow(
                    customer_id=1,
                    customer_code="CUST-001",
                    customer_name="Acme Customer",
                    document_kind="receipt_credit",
                    document_number="RCPT-001",
                    document_date=date(2026, 3, 10),
                    due_date=None,
                    reference_text=None,
                    description="Unapplied receipt",
                    open_amount=Decimal("-25.00"),
                    journal_entry_id=12,
                    source_document_type="customer_receipt",
                    source_document_id=102,
                ),
            ],
            control_balance=Decimal("90.00"),
        )
        service = ARAgingReportService(_fake_uow_factory, lambda session: repo)  # noqa: ARG005

        report = service.get_report(
            OperationalReportFilterDTO(company_id=7, as_of_date=date(2026, 3, 31), posted_only=True)
        )

        self.assertEqual(report.customer_count, 1)
        self.assertEqual(report.total_current, Decimal("25.00"))
        self.assertEqual(report.total_bucket_31_60, Decimal("100.00"))
        self.assertEqual(report.grand_total, Decimal("125.00"))
        self.assertEqual(report.rows[0].total_amount, Decimal("125.00"))
        self.assertEqual(report.warnings[0].code, "ar_control_delta_detected")

    def test_ap_aging_buckets_current_and_overdue(self) -> None:
        repo = _FakeAPAgingRepository(
            rows=[
                APAgingDocumentRow(
                    supplier_id=4,
                    supplier_code="SUP-004",
                    supplier_name="Best Supplier",
                    document_kind="bill",
                    document_number="BILL-001",
                    document_date=date(2026, 3, 1),
                    due_date=date(2026, 4, 5),
                    reference_text="REF-1",
                    description="Bill",
                    open_amount=Decimal("80.00"),
                    journal_entry_id=21,
                    source_document_type="purchase_bill",
                    source_document_id=201,
                ),
                APAgingDocumentRow(
                    supplier_id=4,
                    supplier_code="SUP-004",
                    supplier_name="Best Supplier",
                    document_kind="bill",
                    document_number="BILL-002",
                    document_date=date(2026, 1, 15),
                    due_date=date(2026, 1, 31),
                    reference_text="REF-2",
                    description="Older bill",
                    open_amount=Decimal("40.00"),
                    journal_entry_id=22,
                    source_document_type="purchase_bill",
                    source_document_id=202,
                ),
            ],
            control_balance=Decimal("120.00"),
        )
        service = APAgingReportService(_fake_uow_factory, lambda session: repo)  # noqa: ARG005

        report = service.get_report(
            OperationalReportFilterDTO(company_id=9, as_of_date=date(2026, 3, 31), posted_only=True)
        )

        self.assertEqual(report.supplier_count, 1)
        self.assertEqual(report.total_current, Decimal("80.00"))
        self.assertEqual(report.total_bucket_31_60, Decimal("40.00"))
        self.assertEqual(report.grand_total, Decimal("120.00"))
        self.assertEqual(report.warnings, ())


class CustomerStatementServiceTests(unittest.TestCase):
    def test_statement_builds_opening_activity_and_running_balance(self) -> None:
        repo = _FakeCustomerStatementRepository(
            identity=("CUST-001", "Acme Customer"),
            opening_balance=Decimal("50.00"),
            movements=[
                CustomerStatementMovementRow(
                    movement_date=date(2026, 3, 5),
                    movement_kind="invoice",
                    document_number="INV-002",
                    reference_text="PO-2",
                    description="March invoice",
                    invoice_amount=Decimal("80.00"),
                    receipt_amount=Decimal("0.00"),
                    journal_entry_id=31,
                    source_document_type="sales_invoice",
                    source_document_id=301,
                ),
                CustomerStatementMovementRow(
                    movement_date=date(2026, 3, 12),
                    movement_kind="receipt",
                    document_number="REC-002",
                    reference_text=None,
                    description="Receipt",
                    invoice_amount=Decimal("0.00"),
                    receipt_amount=Decimal("30.00"),
                    journal_entry_id=32,
                    source_document_type="customer_receipt",
                    source_document_id=302,
                ),
            ],
        )
        service = CustomerStatementService(_fake_uow_factory, lambda session: repo)  # noqa: ARG005

        report = service.get_statement(
            OperationalReportFilterDTO(
                company_id=7,
                customer_id=1,
                date_from=date(2026, 3, 1),
                date_to=date(2026, 3, 31),
                posted_only=True,
            )
        )

        self.assertEqual(report.opening_balance, Decimal("50.00"))
        self.assertEqual(report.total_invoices, Decimal("80.00"))
        self.assertEqual(report.total_receipts, Decimal("30.00"))
        self.assertEqual(report.closing_balance, Decimal("100.00"))
        self.assertEqual(report.lines[0].running_balance, Decimal("130.00"))
        self.assertEqual(report.lines[1].running_balance, Decimal("100.00"))


class PayrollSummaryReportServiceTests(unittest.TestCase):
    def test_payroll_summary_totals_runs_employees_and_statutory(self) -> None:
        repo = _FakePayrollSummaryRepository(
            run_rows=[
                PayrollSummaryRunRow(
                    run_id=1,
                    run_reference="PAY-001",
                    run_label="March Main",
                    period_year=2026,
                    period_month=3,
                    run_date=date(2026, 3, 31),
                    payment_date=date(2026, 4, 1),
                    status_code="posted",
                    employee_count=2,
                    gross_pay=Decimal("1000.00"),
                    deductions=Decimal("150.00"),
                    employer_cost=Decimal("120.00"),
                    net_pay=Decimal("850.00"),
                    total_paid=Decimal("600.00"),
                    outstanding_net_pay=Decimal("250.00"),
                    journal_entry_id=41,
                )
            ],
            employee_rows=[
                PayrollSummaryEmployeeRow(
                    employee_id=1,
                    employee_number="E-001",
                    employee_name="Alice Employee",
                    run_id=1,
                    run_employee_id=501,
                    gross_pay=Decimal("500.00"),
                    deductions=Decimal("75.00"),
                    employer_cost=Decimal("60.00"),
                    net_pay=Decimal("425.00"),
                )
            ],
            statutory_rows=[
                PayrollSummaryStatutoryRow(
                    authority_code="cnps",
                    total_due=Decimal("90.00"),
                    total_remitted=Decimal("40.00"),
                    batch_count=1,
                )
            ],
        )
        service = PayrollSummaryReportService(_fake_uow_factory, lambda session: repo)  # noqa: ARG005

        report = service.get_report(
            OperationalReportFilterDTO(
                company_id=12,
                date_from=date(2026, 3, 1),
                date_to=date(2026, 3, 31),
                posted_only=True,
            )
        )

        self.assertTrue(report.has_data)
        self.assertEqual(report.total_gross_pay, Decimal("1000.00"))
        self.assertEqual(report.total_deductions, Decimal("150.00"))
        self.assertEqual(report.total_employer_cost, Decimal("120.00"))
        self.assertEqual(report.total_net_pay, Decimal("850.00"))
        self.assertEqual(report.total_paid, Decimal("600.00"))
        self.assertEqual(report.total_outstanding, Decimal("250.00"))
        self.assertEqual(report.statutory_rows[0].authority_label, "CNPS")
        self.assertEqual(report.statutory_rows[0].outstanding, Decimal("50.00"))


class TreasuryReportServiceTests(unittest.TestCase):
    def test_treasury_report_builds_opening_movement_and_closing(self) -> None:
        repo = _FakeTreasuryReportRepository(
            opening_rows=[
                TreasuryMovementSourceRow(
                    financial_account_id=1,
                    account_code="BANK-1",
                    account_name="Main Bank",
                    account_type_code="bank",
                    transaction_date=date(2026, 2, 28),
                    document_number="OPEN-1",
                    movement_type_label="Bank Receipt",
                    reference_text=None,
                    description="Opening",
                    signed_amount=Decimal("100.00"),
                    journal_entry_id=51,
                    source_document_type="treasury_transaction",
                    source_document_id=601,
                )
            ],
            period_rows=[
                TreasuryMovementSourceRow(
                    financial_account_id=1,
                    account_code="BANK-1",
                    account_name="Main Bank",
                    account_type_code="bank",
                    transaction_date=date(2026, 3, 5),
                    document_number="TRX-1",
                    movement_type_label="Bank Receipt",
                    reference_text=None,
                    description="Receipt",
                    signed_amount=Decimal("40.00"),
                    journal_entry_id=52,
                    source_document_type="treasury_transaction",
                    source_document_id=602,
                ),
                TreasuryMovementSourceRow(
                    financial_account_id=1,
                    account_code="BANK-1",
                    account_name="Main Bank",
                    account_type_code="bank",
                    transaction_date=date(2026, 3, 12),
                    document_number="TRX-2",
                    movement_type_label="Bank Payment",
                    reference_text=None,
                    description="Payment",
                    signed_amount=Decimal("-15.00"),
                    journal_entry_id=53,
                    source_document_type="treasury_transaction",
                    source_document_id=603,
                ),
            ],
        )
        service = TreasuryReportService(_fake_uow_factory, lambda session: repo)  # noqa: ARG005

        report = service.get_report(
            OperationalReportFilterDTO(
                company_id=22,
                date_from=date(2026, 3, 1),
                date_to=date(2026, 3, 31),
                posted_only=True,
            )
        )

        self.assertTrue(report.has_activity)
        self.assertEqual(report.total_opening, Decimal("100.00"))
        self.assertEqual(report.total_inflow, Decimal("40.00"))
        self.assertEqual(report.total_outflow, Decimal("15.00"))
        self.assertEqual(report.total_closing, Decimal("125.00"))
        self.assertEqual(report.account_rows[0].closing_balance, Decimal("125.00"))
        self.assertEqual(report.movement_rows[0].running_balance, Decimal("140.00"))
        self.assertEqual(report.movement_rows[1].running_balance, Decimal("125.00"))


if __name__ == "__main__":
    unittest.main()
