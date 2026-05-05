from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from seeker_accounting.db import model_registry  # noqa: F401
from seeker_accounting.modules.accounting.journals.dto.journal_reversal_dto import ReverseJournalCommand
from seeker_accounting.modules.accounting.journals.models.journal_entry import JournalEntry
from seeker_accounting.modules.accounting.journals.models.journal_entry_line import JournalEntryLine
from seeker_accounting.modules.accounting.journals.services.journal_reversal_service import JournalReversalService
from seeker_accounting.modules.budgeting.services.budget_control_service import BudgetControlService
from seeker_accounting.modules.purchases.services.purchase_bill_posting_service import PurchaseBillPostingService
from seeker_accounting.modules.sales.services.sales_invoice_posting_service import SalesInvoicePostingService
from seeker_accounting.platform.exceptions import ValidationError


class _FakeUnitOfWork:
    def __init__(self, session: object) -> None:
        self.session = session
        self.committed = False

    def __enter__(self) -> _FakeUnitOfWork:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def commit(self) -> None:
        self.committed = True


class _FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.added_all: list[object] = []
        self._next_id = 1000

    def add(self, item: object) -> None:
        if getattr(item, "id", None) is None:
            try:
                setattr(item, "id", self._next_id)
                self._next_id += 1
            except AttributeError:
                pass
        self.added.append(item)

    def add_all(self, items: list[object]) -> None:
        self.added_all.extend(items)

    def flush(self) -> None:
        return None


class _Numbering:
    def issue_next_number(self, session, company_id: int, document_type_code: str) -> str:
        return f"{document_type_code}-001"


class _Permission:
    def require_permission(self, permission_code: str) -> None:
        return None


class _CompanyRepo:
    def __init__(self, session: object) -> None:
        self.session = session

    def get_by_id(self, company_id: int) -> object:
        return SimpleNamespace(id=company_id)


class _PeriodRepo:
    def __init__(self, session: object) -> None:
        self.session = session

    def get_covering_date(self, company_id: int, value: date) -> object:
        return SimpleNamespace(id=20, period_code="2025-01", status_code="OPEN")


class _RoleMappingRepo:
    def __init__(self, account_id: int) -> None:
        self.account_id = account_id

    def get_by_role_code(self, company_id: int, role_code: str) -> object:
        return SimpleNamespace(account_id=self.account_id)


class _TaxMappingRepo:
    def get_by_tax_code(self, company_id: int, tax_code_id: int) -> object | None:
        return None


class _TaxFactService:
    def record_facts_in_session(self, *args, **kwargs) -> None:
        return None


class BudgetControlServiceTests(unittest.TestCase):
    def _service(
        self,
        *,
        control_mode: str,
        approved: bool = True,
        budget_total: Decimal = Decimal("100.00"),
        dimension_budgets: dict[tuple[int | None, int | None], Decimal] | None = None,
        committed: dict[tuple[int | None, int | None], Decimal] | None = None,
        actual: dict[tuple[int | None, int | None], Decimal] | None = None,
    ) -> BudgetControlService:
        session = object()
        project = SimpleNamespace(id=1, company_id=10, budget_control_mode_code=control_mode)
        version = SimpleNamespace(id=5, total_budget_amount=budget_total) if approved else None

        class ProjectRepo:
            def get_by_id(self, project_id: int) -> object | None:
                return project if project_id == 1 else None

        class VersionRepo:
            def get_current_approved(self, project_id: int) -> object | None:
                return version

        class LineRepo:
            def sum_by_version_dimension(self, version_id: int, project_job_id=None, project_cost_code_id=None) -> Decimal:
                return (dimension_budgets or {}).get((project_job_id, project_cost_code_id), Decimal("0.00"))

        class CommitmentLineRepo:
            def sum_open_by_project_dimension(self, project_id: int, project_job_id=None, project_cost_code_id=None, exclude_commitment_id=None) -> Decimal:
                return (committed or {}).get((project_job_id, project_cost_code_id), Decimal("0.00"))

        class ActualsRepo:
            def sum_actual_by_project_dimension(self, company_id: int, project_id: int, project_job_id=None, project_cost_code_id=None) -> Decimal:
                return (actual or {}).get((project_job_id, project_cost_code_id), Decimal("0.00"))

        return BudgetControlService(
            unit_of_work_factory=lambda: _FakeUnitOfWork(session),
            version_repository_factory=lambda _session: VersionRepo(),
            line_repository_factory=lambda _session: LineRepo(),
            project_repository_factory=lambda _session: ProjectRepo(),
            commitment_line_repository_factory=lambda _session: CommitmentLineRepo(),
            actuals_query_repository_factory=lambda _session: ActualsRepo(),
        )

    def test_no_approved_budget_warns_without_blocking_warn_mode(self) -> None:
        service = self._service(control_mode="warn", approved=False)
        check = service.enforce_budget(1, Decimal("10.00"))
        self.assertTrue(check.would_exceed_budget)
        self.assertIn("no approved budget", check.message)

    def test_within_budget_uses_commitments_and_actuals(self) -> None:
        service = self._service(
            control_mode="hard_stop",
            budget_total=Decimal("100.00"),
            committed={(None, None): Decimal("10.00")},
            actual={(None, None): Decimal("20.00")},
        )
        check = service.enforce_budget(1, Decimal("30.00"))
        self.assertFalse(check.would_exceed_budget)
        self.assertEqual(check.remaining_after_request, Decimal("40.00"))

    def test_exceeded_budget_warning_allows(self) -> None:
        service = self._service(
            control_mode="warn",
            budget_total=Decimal("100.00"),
            committed={(None, None): Decimal("80.00")},
            actual={(None, None): Decimal("10.00")},
        )
        check = service.enforce_budget(1, Decimal("20.00"))
        self.assertTrue(check.would_exceed_budget)
        self.assertIn("Warning", check.message)

    def test_exceeded_budget_hard_stop_blocks(self) -> None:
        service = self._service(
            control_mode="hard_stop",
            budget_total=Decimal("100.00"),
            committed={(None, None): Decimal("80.00")},
            actual={(None, None): Decimal("10.00")},
        )
        with self.assertRaises(ValidationError):
            service.enforce_budget(1, Decimal("20.00"))

    def test_dimension_specific_budget_consumption(self) -> None:
        service = self._service(
            control_mode="hard_stop",
            budget_total=Decimal("1000.00"),
            dimension_budgets={(7, 9): Decimal("100.00")},
            actual={(7, 9): Decimal("60.00")},
        )
        check = service.check_budget(
            1,
            Decimal("50.00"),
            project_job_id=7,
            project_cost_code_id=9,
        )
        self.assertEqual(check.budget_total, Decimal("100.00"))
        self.assertTrue(check.would_exceed_budget)

    def test_commitments_and_actuals_consume_budget_together(self) -> None:
        service = self._service(
            control_mode="hard_stop",
            budget_total=Decimal("100.00"),
            committed={(None, 4): Decimal("40.00")},
            actual={(None, 4): Decimal("50.00")},
        )
        with self.assertRaises(ValidationError):
            service.enforce_budget(1, Decimal("15.00"), project_cost_code_id=4)


class SalesPostingDimensionTests(unittest.TestCase):
    def test_project_revenue_source_lines_match_gl_project_revenue(self) -> None:
        session = _FakeSession()
        invoice = SimpleNamespace(
            id=55,
            company_id=10,
            invoice_number="DRAFT-SI",
            invoice_date=date(2025, 1, 15),
            tax_point_date=None,
            status_code="draft",
            payment_status_code="draft",
            contract_id=None,
            project_id=None,
            total_amount=Decimal("300.00"),
            lines=[
                SimpleNamespace(
                    id=1,
                    line_number=1,
                    revenue_account_id=700,
                    line_subtotal_amount=Decimal("100.00"),
                    line_tax_amount=Decimal("0.00"),
                    tax_code_id=None,
                    tax_details=[],
                    contract_id=None,
                    project_id=101,
                    project_job_id=201,
                    project_cost_code_id=301,
                ),
                SimpleNamespace(
                    id=2,
                    line_number=2,
                    revenue_account_id=700,
                    line_subtotal_amount=Decimal("200.00"),
                    line_tax_amount=Decimal("0.00"),
                    tax_code_id=None,
                    tax_details=[],
                    contract_id=None,
                    project_id=102,
                    project_job_id=202,
                    project_cost_code_id=302,
                ),
            ],
        )

        class InvoiceRepo:
            def get_detail(self, company_id: int, invoice_id: int) -> object:
                return invoice

            def save(self, invoice_obj: object) -> None:
                return None

        class JournalRepo:
            def add(self, journal_entry: object) -> None:
                journal_entry.id = 900

            def save(self, journal_entry: object) -> None:
                return None

        class AllocationRepo:
            def get_allocated_totals_for_invoice_ids(self, company_id: int, invoice_ids: list[int], posted_only: bool) -> dict[int, Decimal]:
                return {}

        service = SalesInvoicePostingService(
            unit_of_work_factory=lambda: _FakeUnitOfWork(session),
            app_context=SimpleNamespace(current_user_id=1),
            sales_invoice_repository_factory=lambda _session: InvoiceRepo(),
            journal_entry_repository_factory=lambda _session: JournalRepo(),
            account_repository_factory=lambda _session: SimpleNamespace(),
            fiscal_period_repository_factory=lambda _session: _PeriodRepo(_session),
            account_role_mapping_repository_factory=lambda _session: _RoleMappingRepo(1100),
            tax_code_account_mapping_repository_factory=lambda _session: _TaxMappingRepo(),
            customer_receipt_allocation_repository_factory=lambda _session: AllocationRepo(),
            company_repository_factory=lambda _session: _CompanyRepo(_session),
            numbering_service=_Numbering(),
            permission_service=_Permission(),
            tax_fact_service=_TaxFactService(),
        )

        service.post_invoice(10, 55, actor_user_id=1)
        revenue_lines = [line for line in session.added_all if line.account_id == 700]
        self.assertEqual(len(revenue_lines), 2)
        self.assertEqual(
            {line.project_id: line.credit_amount for line in revenue_lines},
            {101: Decimal("100.00"), 102: Decimal("200.00")},
        )
        ar_lines = [line for line in session.added_all if line.account_id == 1100]
        self.assertEqual(ar_lines[0].project_id, None)


class PurchasePostingDimensionTests(unittest.TestCase):
    def test_project_purchase_source_lines_match_gl_project_expense(self) -> None:
        session = _FakeSession()
        bill = SimpleNamespace(
            id=77,
            company_id=10,
            bill_number="DRAFT-PB",
            bill_date=date(2025, 1, 20),
            tax_point_date=None,
            status_code="draft",
            payment_status_code="draft",
            contract_id=None,
            project_id=None,
            total_amount=Decimal("319.25"),
            lines=[
                SimpleNamespace(
                    id=1,
                    line_number=1,
                    expense_account_id=600,
                    line_subtotal_amount=Decimal("100.00"),
                    line_tax_amount=Decimal("19.25"),
                    tax_code_id=1,
                    tax_code=SimpleNamespace(is_recoverable=False),
                    tax_details=[],
                    contract_id=None,
                    project_id=101,
                    project_job_id=201,
                    project_cost_code_id=301,
                ),
                SimpleNamespace(
                    id=2,
                    line_number=2,
                    expense_account_id=600,
                    line_subtotal_amount=Decimal("200.00"),
                    line_tax_amount=Decimal("0.00"),
                    tax_code_id=None,
                    tax_code=None,
                    tax_details=[],
                    contract_id=None,
                    project_id=102,
                    project_job_id=202,
                    project_cost_code_id=302,
                ),
            ],
        )

        class BillRepo:
            def get_detail(self, company_id: int, bill_id: int) -> object:
                return bill

            def save(self, bill_obj: object) -> None:
                return None

        class JournalRepo:
            def add(self, journal_entry: object) -> None:
                journal_entry.id = 901

            def save(self, journal_entry: object) -> None:
                return None

        class AllocationRepo:
            def get_allocated_totals_for_bill_ids(self, company_id: int, bill_ids: list[int], posted_only: bool) -> dict[int, Decimal]:
                return {}

        service = PurchaseBillPostingService(
            unit_of_work_factory=lambda: _FakeUnitOfWork(session),
            app_context=SimpleNamespace(current_user_id=1),
            purchase_bill_repository_factory=lambda _session: BillRepo(),
            journal_entry_repository_factory=lambda _session: JournalRepo(),
            account_repository_factory=lambda _session: SimpleNamespace(),
            fiscal_period_repository_factory=lambda _session: _PeriodRepo(_session),
            account_role_mapping_repository_factory=lambda _session: _RoleMappingRepo(2100),
            tax_code_account_mapping_repository_factory=lambda _session: _TaxMappingRepo(),
            supplier_payment_allocation_repository_factory=lambda _session: AllocationRepo(),
            company_repository_factory=lambda _session: _CompanyRepo(_session),
            numbering_service=_Numbering(),
            permission_service=_Permission(),
            tax_fact_service=_TaxFactService(),
            budget_control_service=None,
        )

        service.post_bill(10, 77, actor_user_id=1)
        expense_lines = [line for line in session.added_all if line.account_id == 600]
        self.assertEqual(len(expense_lines), 2)
        self.assertEqual(
            {line.project_id: line.debit_amount for line in expense_lines},
            {101: Decimal("119.25"), 102: Decimal("200.00")},
        )
        ap_lines = [line for line in session.added_all if line.account_id == 2100]
        self.assertEqual(ap_lines[0].project_id, None)


class JournalReversalDimensionTests(unittest.TestCase):
    def test_reversal_preserves_project_dimensions(self) -> None:
        session = _FakeSession()
        source = SimpleNamespace(
            id=300,
            entry_number="JE-300",
            status_code="POSTED",
            source_document_type="manual_journal",
            journal_type_code="GENERAL",
            lines=[
                SimpleNamespace(
                    line_number=1,
                    account_id=600,
                    debit_amount=Decimal("50.00"),
                    credit_amount=Decimal("0.00"),
                    line_description="Project cost",
                    contract_id=11,
                    project_id=101,
                    project_job_id=201,
                    project_cost_code_id=301,
                ),
                SimpleNamespace(
                    line_number=2,
                    account_id=100,
                    debit_amount=Decimal("0.00"),
                    credit_amount=Decimal("50.00"),
                    line_description="Cash",
                    contract_id=None,
                    project_id=None,
                    project_job_id=None,
                    project_cost_code_id=None,
                ),
            ],
        )

        class JournalRepo:
            def get_detail(self, company_id: int, journal_entry_id: int) -> object:
                return source

        service = JournalReversalService(
            unit_of_work_factory=lambda: _FakeUnitOfWork(session),
            app_context=SimpleNamespace(current_user_id=1),
            journal_entry_repository_factory=lambda _session: JournalRepo(),
            fiscal_period_repository_factory=lambda _session: _PeriodRepo(_session),
            company_repository_factory=lambda _session: _CompanyRepo(_session),
            numbering_service=_Numbering(),
        )

        service.reverse_journal(
            10,
            300,
            ReverseJournalCommand(reversal_date=date(2025, 2, 1), reason="Correction"),
            actor_user_id=1,
        )
        reversal_lines = [item for item in session.added if isinstance(item, JournalEntryLine)]
        project_line = next(line for line in reversal_lines if line.account_id == 600)
        self.assertEqual(project_line.project_id, 101)
        self.assertEqual(project_line.project_job_id, 201)
        self.assertEqual(project_line.project_cost_code_id, 301)
        self.assertEqual(project_line.debit_amount, Decimal("0.00"))
        self.assertEqual(project_line.credit_amount, Decimal("50.00"))


if __name__ == "__main__":
    unittest.main()
