"""
Deterministic audit scenario to verify extension slices 14-16 after defect fixes.

Defects being verified:
  1. ContractService  — CustomerRepository.get_by_id now called with (company_id, customer_id)
  2. ProjectService   — CustomerRepository.get_by_id now called with (company_id, customer_id)
  3. ProjectCostCodeService — AccountRepository.get_by_id now called with (company_id, account_id)

Expected reporting totals:
  current_contract_amount          = 105,000
  approved_budget                  =  90,000
  approved_commitment              =  10,000
  actual_cost_total                =  30,000
  billed_revenue                   =  40,000
  total_exposure                   =  40,000
  remaining_budget_before_commit   =  60,000
  remaining_budget_after_commit    =  50,000
  variance                         =  60,000
  gross_margin                     =  10,000
"""
from __future__ import annotations

import sys
import os
from datetime import date, datetime
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.setdefault("SEEKER_TESTING", "1")

from contextlib import contextmanager
from sqlalchemy.orm import Session
from seeker_accounting.config.settings import load_settings
from seeker_accounting.db.engine import create_database_engine
from seeker_accounting.db.session import create_session_factory

# Import all models needed for direct seeding
from seeker_accounting.modules.companies.models.company import Company
from seeker_accounting.modules.companies.models.company_project_preference import CompanyProjectPreference
from seeker_accounting.modules.customers.models.customer import Customer
from seeker_accounting.modules.suppliers.models.supplier import Supplier
from seeker_accounting.modules.accounting.reference_data.models.currency import Currency
from seeker_accounting.modules.accounting.reference_data.models.country import Country
from seeker_accounting.modules.accounting.reference_data.models.account_class import AccountClass
from seeker_accounting.modules.accounting.reference_data.models.account_type import AccountType
from seeker_accounting.modules.accounting.chart_of_accounts.models.account import Account
from seeker_accounting.modules.accounting.fiscal_periods.models.fiscal_year import FiscalYear
from seeker_accounting.modules.accounting.fiscal_periods.models.fiscal_period import FiscalPeriod
from seeker_accounting.modules.contracts_projects.models.contract import Contract
from seeker_accounting.modules.contracts_projects.models.contract_change_order import ContractChangeOrder
from seeker_accounting.modules.contracts_projects.models.project import Project
from seeker_accounting.modules.contracts_projects.models.project_cost_code import ProjectCostCode
from seeker_accounting.modules.contracts_projects.models.project_job import ProjectJob
from seeker_accounting.modules.purchases.models.purchase_bill import PurchaseBill
from seeker_accounting.modules.purchases.models.purchase_bill_line import PurchaseBillLine
from seeker_accounting.modules.treasury.models.treasury_transaction import TreasuryTransaction
from seeker_accounting.modules.treasury.models.treasury_transaction_line import TreasuryTransactionLine
from seeker_accounting.modules.treasury.models.financial_account import FinancialAccount
from seeker_accounting.modules.inventory.models.inventory_location import InventoryLocation
from seeker_accounting.modules.inventory.models.item import Item
from seeker_accounting.modules.inventory.models.inventory_document import InventoryDocument
from seeker_accounting.modules.inventory.models.inventory_document_line import InventoryDocumentLine
from seeker_accounting.modules.payroll.models.payroll_run import PayrollRun
from seeker_accounting.modules.payroll.models.payroll_run_employee import PayrollRunEmployee
from seeker_accounting.modules.payroll.models.payroll_run_employee_project_allocation import PayrollRunEmployeeProjectAllocation
from seeker_accounting.modules.accounting.journals.models.journal_entry import JournalEntry
from seeker_accounting.modules.accounting.journals.models.journal_entry_line import JournalEntryLine
from seeker_accounting.modules.sales.models.sales_invoice import SalesInvoice
from seeker_accounting.modules.sales.models.sales_invoice_line import SalesInvoiceLine
from seeker_accounting.modules.budgeting.models.project_budget_version import ProjectBudgetVersion
from seeker_accounting.modules.budgeting.models.project_budget_line import ProjectBudgetLine
from seeker_accounting.modules.job_costing.models.project_commitment import ProjectCommitment
from seeker_accounting.modules.job_costing.models.project_commitment_line import ProjectCommitmentLine

# Service-layer imports
from shared.bootstrap import bootstrap_script_runtime
from seeker_accounting.modules.contracts_projects.dto.contract_dto import CreateContractCommand
from seeker_accounting.modules.contracts_projects.dto.project_dto import CreateProjectCommand
from seeker_accounting.modules.contracts_projects.dto.project_cost_code_commands import (
    CreateProjectCostCodeCommand,
    UpdateProjectCostCodeCommand,
)

# ── Helpers ──────────────────────────────────────────────────────────────────

PASS = 0
FAIL = 0

def check(label: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        msg = f"  FAIL  {label}"
        if detail:
            msg += f"  ({detail})"
        print(msg)

def dec(v) -> Decimal:
    return Decimal(str(v))


# ── Foundation seeding ───────────────────────────────────────────────────────

def seed_foundation(s: Session) -> dict:
    """Seed all foundation data and return a dict of IDs."""

    # Currency
    xaf = s.get(Currency, "XAF")
    if xaf is None:
        xaf = Currency(code="XAF", name="Central African CFA Franc", symbol="FCFA", decimal_places=0, is_active=True)
        s.add(xaf)
        s.flush()

    # Country
    cm = s.get(Country, "CM")
    if cm is None:
        cm = Country(code="CM", name="Cameroon", is_active=True)
        s.add(cm)
        s.flush()

    # Company
    company = Company(
        legal_name="Audit Corp SARL",
        display_name="Audit Corp",
        country_code="CM",
        base_currency_code="XAF",
        is_active=True,
    )
    s.add(company)
    s.flush()
    co_id = company.id

    # Project preference
    pref = CompanyProjectPreference(
        company_id=co_id,
        allow_projects_without_contract=True,
        default_budget_control_mode_code="warn",
        default_commitment_control_mode_code="warn",
        budget_warning_percent_threshold=Decimal("80"),
        require_job_on_cost_posting=False,
        require_cost_code_on_cost_posting=False,
    )
    s.add(pref)

    # Customer
    customer = Customer(
        company_id=co_id,
        customer_code="C001",
        display_name="Test Customer Alpha",
        is_active=True,
    )
    s.add(customer)
    s.flush()
    cust_id = customer.id

    # Supplier
    supplier = Supplier(
        company_id=co_id,
        supplier_code="S001",
        display_name="Test Supplier Beta",
        is_active=True,
    )
    s.add(supplier)
    s.flush()
    supp_id = supplier.id

    # Account class + type
    acl = AccountClass(code="EXP", name="Expenses", display_order=5, is_active=True)
    s.add(acl)
    s.flush()

    at_expense = AccountType(
        code="OPS_EXP",
        name="Operating Expense",
        normal_balance="debit",
        financial_statement_section_code="EXPENSE",
        is_active=True,
    )
    s.add(at_expense)
    s.flush()

    # Account (expense)
    account = Account(
        company_id=co_id,
        account_code="6100",
        account_name="Project Expenses",
        account_class_id=acl.id,
        account_type_id=at_expense.id,
        normal_balance="debit",
        is_active=True,
    )
    s.add(account)
    s.flush()
    acct_id = account.id

    # Revenue account class + type
    acl_rev = AccountClass(code="REV", name="Revenue", display_order=4, is_active=True)
    s.add(acl_rev)
    s.flush()

    at_revenue = AccountType(
        code="SVC_REV",
        name="Service Revenue",
        normal_balance="credit",
        financial_statement_section_code="REVENUE",
        is_active=True,
    )
    s.add(at_revenue)
    s.flush()

    rev_account = Account(
        company_id=co_id,
        account_code="7100",
        account_name="Service Revenue",
        account_class_id=acl_rev.id,
        account_type_id=at_revenue.id,
        normal_balance="credit",
        is_active=True,
    )
    s.add(rev_account)
    s.flush()
    rev_acct_id = rev_account.id

    # Fiscal year + period (needed for journal entries)
    fy = FiscalYear(
        company_id=co_id,
        year_code="FY2025",
        year_name="Fiscal Year 2025",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
        status_code="open",
        is_active=True,
    )
    s.add(fy)
    s.flush()

    fp = FiscalPeriod(
        company_id=co_id,
        fiscal_year_id=fy.id,
        period_number=1,
        period_code="2025-01",
        period_name="January 2025",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
        status_code="open",
        is_adjustment_period=False,
    )
    s.add(fp)
    s.flush()

    # Financial account (for treasury seeding)
    fin_acct = FinancialAccount(
        company_id=co_id,
        account_code="CASH1",
        name="Main Cash",
        financial_account_type_code="cash",
        gl_account_id=account.id,
        currency_code="XAF",
        is_active=True,
    )
    s.add(fin_acct)
    s.flush()

    s.commit()

    return dict(
        co_id=co_id,
        cust_id=cust_id,
        supp_id=supp_id,
        acct_id=acct_id,
        rev_acct_id=rev_acct_id,
        fy_id=fy.id,
        fp_id=fp.id,
        fin_acct_id=fin_acct.id,
    )


# ── Phase 1: Service-exercised contract / project / cost-code ────────────────

def test_defect_1_contract_service(reg, ids: dict) -> int:
    """Exercise ContractService create, list, detail — Defect #1 fix verification."""
    print("\n── DEFECT #1: ContractService (CustomerRepository.get_by_id) ──")
    svc = reg.contract_service
    co_id, cust_id = ids["co_id"], ids["cust_id"]

    # Create
    cmd = CreateContractCommand(
        company_id=co_id,
        contract_number="CTR-001",
        contract_title="Alpha Build Contract",
        customer_id=cust_id,
        contract_type_code="fixed_price",
        currency_code="XAF",
        base_contract_amount=Decimal("100000"),
        start_date=datetime(2025, 1, 1),
        planned_end_date=datetime(2025, 12, 31),
    )
    dto = svc.create_contract(cmd)
    check("contract_create", dto is not None and dto.id > 0, f"id={dto.id if dto else 'None'}")
    check("contract_create_customer_name", dto.customer_display_name == "Test Customer Alpha",
          f"got={dto.customer_display_name!r}")
    contract_id = dto.id

    # Activate
    svc.activate_contract(contract_id)

    # List
    items = svc.list_contracts(co_id)
    check("contract_list", len(items) == 1, f"count={len(items)}")
    check("contract_list_customer_name", items[0].customer_display_name == "Test Customer Alpha",
          f"got={items[0].customer_display_name!r}")

    # Detail
    detail = svc.get_contract_detail(contract_id)
    check("contract_detail", detail.id == contract_id)
    check("contract_detail_customer_name", detail.customer_display_name == "Test Customer Alpha",
          f"got={detail.customer_display_name!r}")
    check("contract_detail_base_amount", detail.base_contract_amount == Decimal("100000"),
          f"got={detail.base_contract_amount}")

    return contract_id


def test_defect_2_project_service(reg, ids: dict, contract_id: int) -> int:
    """Exercise ProjectService create, list, detail — Defect #2 fix verification."""
    print("\n── DEFECT #2: ProjectService (CustomerRepository.get_by_id) ──")
    svc = reg.project_service
    co_id, cust_id = ids["co_id"], ids["cust_id"]

    cmd = CreateProjectCommand(
        company_id=co_id,
        project_code="PRJ-001",
        project_name="Alpha Construction",
        contract_id=contract_id,
        customer_id=cust_id,
        project_type_code="external",
        currency_code="XAF",
        start_date=datetime(2025, 1, 1),
        planned_end_date=datetime(2025, 12, 31),
        budget_control_mode_code="warn",
    )
    dto = svc.create_project(cmd)
    check("project_create", dto is not None and dto.id > 0, f"id={dto.id if dto else 'None'}")
    check("project_create_customer_name", dto.customer_display_name == "Test Customer Alpha",
          f"got={dto.customer_display_name!r}")
    project_id = dto.id

    # Activate
    svc.activate_project(project_id)

    # List
    items = svc.list_projects(co_id)
    check("project_list", len(items) == 1, f"count={len(items)}")
    check("project_list_customer_name", items[0].customer_display_name == "Test Customer Alpha",
          f"got={items[0].customer_display_name!r}")

    # Detail
    detail = svc.get_project_detail(project_id)
    check("project_detail", detail.id == project_id)
    check("project_detail_customer_name", detail.customer_display_name == "Test Customer Alpha",
          f"got={detail.customer_display_name!r}")
    check("project_detail_contract_number", detail.contract_number == "CTR-001",
          f"got={detail.contract_number!r}")

    return project_id


def test_defect_3_cost_code_service(reg, ids: dict) -> int:
    """Exercise ProjectCostCodeService create, update, detail — Defect #3 fix verification."""
    print("\n── DEFECT #3: ProjectCostCodeService (AccountRepository.get_by_id) ──")
    svc = reg.project_cost_code_service
    co_id, acct_id = ids["co_id"], ids["acct_id"]

    # Create with default_account_id
    cmd = CreateProjectCostCodeCommand(
        company_id=co_id,
        code="LAB",
        name="Labour",
        cost_code_type_code="labour",
        default_account_id=acct_id,
    )
    dto = svc.create_cost_code(cmd)
    check("costcode_create", dto is not None and dto.id > 0, f"id={dto.id if dto else 'None'}")
    check("costcode_create_account_code", dto.default_account_code == "6100",
          f"got={dto.default_account_code!r}")
    cc_id = dto.id

    # Update with same default_account_id
    ucmd = UpdateProjectCostCodeCommand(
        name="Labour Updated",
        cost_code_type_code="labour",
        default_account_id=acct_id,
    )
    udto = svc.update_cost_code(cc_id, ucmd)
    check("costcode_update", udto.name == "Labour Updated", f"got={udto.name!r}")
    check("costcode_update_account_code", udto.default_account_code == "6100",
          f"got={udto.default_account_code!r}")

    # Detail
    detail = svc.get_cost_code_detail(cc_id)
    check("costcode_detail", detail.id == cc_id)
    check("costcode_detail_account_code", detail.default_account_code == "6100",
          f"got={detail.default_account_code!r}")

    # List
    items = svc.list_cost_codes(co_id)
    check("costcode_list", len(items) >= 1, f"count={len(items)}")
    check("costcode_list_account_code", items[0].default_account_code == "6100",
          f"got={items[0].default_account_code!r}")

    return cc_id


# ── Phase 2: Seed change orders, budgets, commitments, source docs ───────────

def seed_change_order(s: Session, co_id: int, contract_id: int) -> None:
    """Seed an approved change order with delta = +5,000."""
    co = ContractChangeOrder(
        company_id=co_id,
        contract_id=contract_id,
        change_order_number="CO-001",
        change_order_date=date(2025, 3, 1),
        status_code="approved",
        change_type_code="scope",
        description="Additional scope",
        contract_amount_delta=Decimal("5000"),
        approved_at=datetime(2025, 3, 1, 12, 0, 0),
    )
    s.add(co)
    s.commit()


def seed_budget(s: Session, co_id: int, project_id: int, cc_id: int) -> None:
    """Seed approved budget version with 3 lines totaling 90,000."""
    bv = ProjectBudgetVersion(
        company_id=co_id,
        project_id=project_id,
        version_number=1,
        version_name="Initial Budget",
        version_type_code="original",
        status_code="approved",
        budget_date=date(2025, 1, 15),
        total_budget_amount=Decimal("90000"),
        approved_at=datetime(2025, 1, 15, 10, 0, 0),
        approved_by_user_id=1,
    )
    s.add(bv)
    s.flush()

    for i, (amt, desc) in enumerate([(40000, "Labour budget"), (30000, "Materials budget"), (20000, "Equipment budget")], 1):
        s.add(ProjectBudgetLine(
            project_budget_version_id=bv.id,
            line_number=i,
            project_cost_code_id=cc_id,
            line_amount=Decimal(str(amt)),
            description=desc,
        ))
    s.commit()


def seed_commitment(s: Session, co_id: int, project_id: int, cc_id: int, supp_id: int) -> None:
    """Seed approved commitment with 1 line totaling 10,000."""
    cm = ProjectCommitment(
        company_id=co_id,
        project_id=project_id,
        commitment_number="CMT-001",
        commitment_type_code="purchase_order",
        commitment_date=date(2025, 2, 1),
        currency_code="XAF",
        supplier_id=supp_id,
        status_code="approved",
        total_amount=Decimal("10000"),
        approved_at=datetime(2025, 2, 1, 10, 0, 0),
        approved_by_user_id=1,
    )
    s.add(cm)
    s.flush()

    s.add(ProjectCommitmentLine(
        project_commitment_id=cm.id,
        line_number=1,
        project_cost_code_id=cc_id,
        line_amount=Decimal("10000"),
        description="Subcontract materials",
    ))
    s.commit()


def seed_job(s: Session, co_id: int, project_id: int) -> int:
    """Seed a project job."""
    job = ProjectJob(
        company_id=co_id,
        project_id=project_id,
        job_code="JOB-01",
        job_name="Foundation Work",
        status_code="active",
        allow_direct_cost_posting=True,
    )
    s.add(job)
    s.flush()
    s.commit()
    return job.id


def seed_actual_costs(s: Session, ids: dict, project_id: int, cc_id: int, job_id: int) -> None:
    """
    Seed 5 actual cost sources totaling 30,000:
      purchase_bill:   12,000
      treasury_payment: 3,000
      inventory_issue:  5,000
      payroll_alloc:    2,000
      manual_journal:   8,000
    """
    co_id = ids["co_id"]
    supp_id = ids["supp_id"]
    acct_id = ids["acct_id"]
    fp_id = ids["fp_id"]
    fin_acct_id = ids["fin_acct_id"]

    now = datetime(2025, 1, 20, 12, 0, 0)

    # 1. Purchase bill — 12,000
    pb = PurchaseBill(
        company_id=co_id,
        bill_number="PB-001",
        supplier_id=supp_id,
        bill_date=date(2025, 1, 15),
        due_date=date(2025, 2, 15),
        currency_code="XAF",
        status_code="posted",
        payment_status_code="unpaid",
        subtotal_amount=Decimal("12000"),
        tax_amount=Decimal("0"),
        total_amount=Decimal("12000"),
        project_id=project_id,
        posted_at=now,
    )
    s.add(pb)
    s.flush()
    s.add(PurchaseBillLine(
        purchase_bill_id=pb.id,
        line_number=1,
        description="Materials purchase",
        quantity=Decimal("1"),
        unit_cost=Decimal("12000"),
        expense_account_id=acct_id,
        line_subtotal_amount=Decimal("12000"),
        line_tax_amount=Decimal("0"),
        line_total_amount=Decimal("12000"),
        project_id=project_id,
        project_job_id=job_id,
        project_cost_code_id=cc_id,
    ))

    # 2. Treasury payment — 3,000
    tt = TreasuryTransaction(
        company_id=co_id,
        transaction_number="TT-001",
        transaction_type_code="cash_payment",
        financial_account_id=fin_acct_id,
        transaction_date=date(2025, 1, 16),
        currency_code="XAF",
        total_amount=Decimal("3000"),
        status_code="posted",
        project_id=project_id,
        posted_at=now,
    )
    s.add(tt)
    s.flush()
    s.add(TreasuryTransactionLine(
        treasury_transaction_id=tt.id,
        line_number=1,
        account_id=acct_id,
        amount=Decimal("3000"),
        project_id=project_id,
        project_job_id=job_id,
        project_cost_code_id=cc_id,
    ))

    # 3. Inventory issue — 5,000
    loc = InventoryLocation(company_id=co_id, code="WH1", name="Main Warehouse", is_active=True)
    s.add(loc)
    s.flush()

    item = Item(
        company_id=co_id,
        item_code="ITEM-01",
        item_name="Steel Beam",
        item_type_code="inventory",
        is_active=True,
    )
    s.add(item)
    s.flush()

    idoc = InventoryDocument(
        company_id=co_id,
        document_number="INV-001",
        document_type_code="issue",
        document_date=date(2025, 1, 17),
        status_code="posted",
        location_id=loc.id,
        total_value=Decimal("5000"),
        project_id=project_id,
        posted_at=now,
    )
    s.add(idoc)
    s.flush()
    s.add(InventoryDocumentLine(
        inventory_document_id=idoc.id,
        line_number=1,
        item_id=item.id,
        quantity=Decimal("10"),
        unit_cost=Decimal("500"),
        line_amount=Decimal("5000"),
        project_id=project_id,
        project_job_id=job_id,
        project_cost_code_id=cc_id,
    ))

    # 4. Payroll allocation — 2,000
    pr = PayrollRun(
        company_id=co_id,
        run_reference="PR-2025-01",
        run_label="January Payroll",
        period_year=2025,
        period_month=1,
        status_code="approved",
        currency_code="XAF",
        run_date=date(2025, 1, 31),
    )
    s.add(pr)
    s.flush()

    pre = PayrollRunEmployee(
        company_id=co_id,
        run_id=pr.id,
        employee_id=1,
        status_code="included",
    )
    s.add(pre)
    s.flush()

    s.add(PayrollRunEmployeeProjectAllocation(
        payroll_run_employee_id=pre.id,
        line_number=1,
        project_id=project_id,
        project_job_id=job_id,
        project_cost_code_id=cc_id,
        allocation_basis_code="percent",
        allocation_percent=Decimal("100"),
        allocated_cost_amount=Decimal("2000"),
    ))

    # 5. Manual journal expense — 8,000
    je = JournalEntry(
        company_id=co_id,
        fiscal_period_id=fp_id,
        entry_number="JE-001",
        entry_date=date(2025, 1, 20),
        journal_type_code="GJ",
        status_code="POSTED",
        source_module_code=None,
        posted_at=now,
    )
    s.add(je)
    s.flush()

    # Debit expense line (project-linked)
    s.add(JournalEntryLine(
        journal_entry_id=je.id,
        line_number=1,
        account_id=acct_id,
        debit_amount=Decimal("8000"),
        credit_amount=Decimal("0"),
        project_id=project_id,
        project_job_id=job_id,
        project_cost_code_id=cc_id,
    ))
    # Credit balancing line (not project-linked)
    s.add(JournalEntryLine(
        journal_entry_id=je.id,
        line_number=2,
        account_id=acct_id,
        debit_amount=Decimal("0"),
        credit_amount=Decimal("8000"),
    ))

    s.commit()


def seed_revenue(s: Session, ids: dict, project_id: int, cc_id: int, job_id: int) -> None:
    """Seed a posted sales invoice with revenue = 40,000."""
    co_id = ids["co_id"]
    cust_id = ids["cust_id"]
    rev_acct_id = ids["rev_acct_id"]
    now = datetime(2025, 1, 25, 12, 0, 0)

    si = SalesInvoice(
        company_id=co_id,
        invoice_number="SI-001",
        customer_id=cust_id,
        invoice_date=date(2025, 1, 25),
        due_date=date(2025, 2, 25),
        currency_code="XAF",
        status_code="posted",
        payment_status_code="unpaid",
        subtotal_amount=Decimal("40000"),
        tax_amount=Decimal("0"),
        total_amount=Decimal("40000"),
        project_id=project_id,
        posted_at=now,
    )
    s.add(si)
    s.flush()
    s.add(SalesInvoiceLine(
        sales_invoice_id=si.id,
        line_number=1,
        description="Progress billing",
        quantity=Decimal("1"),
        unit_price=Decimal("40000"),
        revenue_account_id=rev_acct_id,
        line_subtotal_amount=Decimal("40000"),
        line_tax_amount=Decimal("0"),
        line_total_amount=Decimal("40000"),
        project_id=project_id,
        project_job_id=job_id,
        project_cost_code_id=cc_id,
    ))
    s.commit()


# ── Phase 3: Reporting verification ─────────────────────────────────────────

def test_reporting(reg, ids: dict, project_id: int, contract_id: int) -> None:
    """Verify all reporting totals match expected deterministic values."""
    print("\n── REPORTING VERIFICATION ──")
    co_id = ids["co_id"]

    # Budget variance
    brs = reg.budget_reporting_service
    vs = brs.get_project_variance_summary(co_id, project_id)
    check("rpt_approved_budget", vs.approved_budget_amount == dec(90000),
          f"got={vs.approved_budget_amount}")
    check("rpt_actual_cost", vs.actual_cost_amount == dec(30000),
          f"got={vs.actual_cost_amount}")
    check("rpt_approved_commitment", vs.approved_commitment_amount == dec(10000),
          f"got={vs.approved_commitment_amount}")
    check("rpt_total_exposure", vs.total_exposure_amount == dec(40000),
          f"got={vs.total_exposure_amount}")
    check("rpt_remaining_budget", vs.remaining_budget_amount == dec(60000),
          f"got={vs.remaining_budget_amount}")
    check("rpt_remaining_after_commit", vs.remaining_budget_after_commitments_amount == dec(50000),
          f"got={vs.remaining_budget_after_commitments_amount}")
    check("rpt_variance", vs.variance_amount == dec(60000),
          f"got={vs.variance_amount}")
    check("rpt_billed_revenue", vs.billed_revenue_amount == dec(40000),
          f"got={vs.billed_revenue_amount}")
    check("rpt_margin", vs.margin_amount == dec(10000),
          f"got={vs.margin_amount}")

    # Contract summary
    crs = reg.contract_reporting_service
    cs = crs.get_contract_summary(co_id, contract_id)
    check("rpt_base_contract", cs.base_contract_amount == dec(100000),
          f"got={cs.base_contract_amount}")
    check("rpt_co_delta", cs.approved_change_order_delta_total == dec(5000),
          f"got={cs.approved_change_order_delta_total}")
    check("rpt_current_contract", cs.current_contract_amount == dec(105000),
          f"got={cs.current_contract_amount}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    global PASS, FAIL

    settings = load_settings()
    engine = create_database_engine(settings)
    session_factory = create_session_factory(engine)

    @contextmanager
    def scoped_session():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    print("Seeding foundation data...")
    with scoped_session() as session:
        ids = seed_foundation(session)

    print("Bootstrapping service registry...")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    bootstrap = bootstrap_script_runtime(app)
    reg = bootstrap.service_registry

    # Phase 1: Exercise the three defective services
    contract_id = test_defect_1_contract_service(reg, ids)
    project_id = test_defect_2_project_service(reg, ids, contract_id)
    cc_id = test_defect_3_cost_code_service(reg, ids)

    # Phase 2: Seed supporting data for reporting
    print("\nSeeding change order, budget, commitment, jobs...")
    with scoped_session() as session:
        seed_change_order(session, ids["co_id"], contract_id)
        job_id = seed_job(session, ids["co_id"], project_id)
        seed_budget(session, ids["co_id"], project_id, cc_id)
        seed_commitment(session, ids["co_id"], project_id, cc_id, ids["supp_id"])
        seed_actual_costs(session, ids, project_id, cc_id, job_id)
        seed_revenue(session, ids, project_id, cc_id, job_id)

    # Phase 3: Reporting
    test_reporting(reg, ids, project_id, contract_id)

    print(f"\n{'='*60}")
    print(f"RESULT: PASS={PASS} FAIL={FAIL}")
    print(f"{'='*60}")
    return 1 if FAIL > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
