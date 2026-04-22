"""
Seed a comprehensive Demo Organisation into Seeker Accounting.

Creates:
  - Demo company (Cameroon / XAF / OHADA)
  - Admin user (admin / sysadmin) + role-based user accounts
  - Full OHADA chart of accounts
  - 3 fiscal years (2024, 2025, 2026) with monthly periods
  - Tax codes, payment terms, document sequences
  - Financial accounts (bank + cash)
  - 48 third parties (28 customers, 20 suppliers)
  - 17 employees across 5 departments
  - 14 contracts + 38 projects + jobs + cost codes + budgets
  - 14 fixed assets (some already depreciating)
  - Inventory items + stock documents
  - ~720 posted journal entries spanning 3 years
  - Sales invoices, purchase bills, receipts, payments

Usage:
    cd "Seeker Accounting"
    .venv\\Scripts\\python.exe scripts/seed_demo_org.py
"""
from __future__ import annotations

import io
import random
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from PySide6.QtWidgets import QApplication

import bcrypt

from shared.bootstrap import bootstrap_script_runtime
from seeker_accounting.modules.administration.rbac_catalog import SYSTEM_PERMISSION_BY_CODE

# ---------------------------------------------------------------------------
# Deterministic random for reproducibility
# ---------------------------------------------------------------------------
RNG = random.Random(42)

NOW = datetime(2026, 4, 1, 12, 0, 0)


def _utcnow():
    return NOW


def _hash(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


# ---------------------------------------------------------------------------
# Reference data helpers
# ---------------------------------------------------------------------------

def _ensure_country_and_currency(session):
    from seeker_accounting.modules.accounting.reference_data.models.country import Country
    from seeker_accounting.modules.accounting.reference_data.models.currency import Currency
    if not session.get(Country, "CM"):
        session.add(Country(code="CM", name="Cameroon", is_active=True))
    if not session.get(Currency, "XAF"):
        session.add(Currency(code="XAF", name="CFA Franc BEAC", symbol="FCFA", decimal_places=0, is_active=True))
    session.flush()


# ---------------------------------------------------------------------------
# Main seed logic
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("  Seeker Accounting — Demo Organisation Seed Script")
    print("=" * 70)

    app = QApplication.instance() or QApplication([])
    bootstrap = bootstrap_script_runtime(
        app,
        permission_snapshot=tuple(SYSTEM_PERMISSION_BY_CODE.keys()),
    )
    reg = bootstrap.service_registry

    # -- Step 1: Seed global reference data --------------------------------
    print("\n[1/12] Seeding global reference data...")
    reg.chart_seed_service.ensure_global_chart_reference_seed()
    print("  OK — account classes, types, depreciation methods seeded")

    # -- Step 2: Create company --------------------------------------------
    print("\n[2/12] Creating Demo Organisation...")
    from seeker_accounting.modules.companies.dto.company_commands import CreateCompanyCommand
    from seeker_accounting.modules.companies.models.company import Company as CompanyModel

    with reg.session_context.unit_of_work_factory() as uow:
        _ensure_country_and_currency(uow.session)
        # Check if company already exists
        existing = uow.session.query(CompanyModel).filter_by(legal_name="Afritech Solutions SARL").first()
        if existing:
            print(f"  Company already exists (ID={existing.id}). Delete database to re-seed.")
            print("  Aborting.")
            return
        uow.commit()

    company = reg.company_service.create_company(CreateCompanyCommand(
        legal_name="Afritech Solutions SARL",
        display_name="Afritech Solutions",
        registration_number="RC/DLA/2023/A-00412",
        tax_identifier="M098765432A",
        cnps_employer_number="CNPS-ER-00412",
        phone="+237 233 42 55 00",
        email="contact@afritech-solutions.cm",
        website="www.afritech-solutions.cm",
        sector_of_operation="Technology Services & Civil Engineering",
        address_line_1="123 Boulevard de la Liberté",
        address_line_2="Immeuble Afritech, 3ème étage",
        city="Douala",
        region="Littoral",
        country_code="CM",
        base_currency_code="XAF",
    ))
    CID = company.id
    print(f"  OK — Company ID={CID}: {company.legal_name}")

    # -- Step 3: Seed chart of accounts ------------------------------------
    print("\n[3/12] Seeding OHADA chart of accounts...")
    reg.company_seed_service.seed_built_in_chart(CID)
    accounts = reg.chart_of_accounts_service.list_accounts(CID, active_only=True)
    acct_map = {a.account_code: a for a in accounts}
    print(f"  OK — {len(accounts)} accounts seeded")

    def acct_id(code: str) -> int:
        """Look up account ID by OHADA code prefix."""
        if code in acct_map:
            return acct_map[code].id
        for a in accounts:
            if a.account_code.startswith(code) and a.is_active:
                return a.id
        raise ValueError(f"Account code '{code}' not found")

    # =====================================================================
    # From here, we do direct ORM inserts for speed and volume
    # =====================================================================
    from sqlalchemy import text
    from seeker_accounting.modules.accounting.fiscal_periods.models.fiscal_year import FiscalYear
    from seeker_accounting.modules.accounting.fiscal_periods.models.fiscal_period import FiscalPeriod
    from seeker_accounting.modules.accounting.journals.models.journal_entry import JournalEntry
    from seeker_accounting.modules.accounting.journals.models.journal_entry_line import JournalEntryLine
    from seeker_accounting.modules.accounting.reference_data.models.payment_term import PaymentTerm
    from seeker_accounting.modules.accounting.reference_data.models.tax_code import TaxCode
    from seeker_accounting.modules.accounting.reference_data.models.document_sequence import DocumentSequence
    from seeker_accounting.modules.accounting.reference_data.models.account_role_mapping import AccountRoleMapping
    from seeker_accounting.modules.administration.models.user import User
    from seeker_accounting.modules.administration.models.role import Role
    from seeker_accounting.modules.administration.models.permission import Permission
    from seeker_accounting.modules.administration.models.role_permission import RolePermission
    from seeker_accounting.modules.administration.models.user_role import UserRole
    from seeker_accounting.modules.administration.models.user_company_access import UserCompanyAccess
    from seeker_accounting.modules.customers.models.customer_group import CustomerGroup
    from seeker_accounting.modules.customers.models.customer import Customer
    from seeker_accounting.modules.suppliers.models.supplier_group import SupplierGroup
    from seeker_accounting.modules.suppliers.models.supplier import Supplier
    from seeker_accounting.modules.treasury.models.financial_account import FinancialAccount
    from seeker_accounting.modules.treasury.models.treasury_transaction import TreasuryTransaction
    from seeker_accounting.modules.treasury.models.treasury_transaction_line import TreasuryTransactionLine
    from seeker_accounting.modules.sales.models.sales_invoice import SalesInvoice
    from seeker_accounting.modules.sales.models.sales_invoice_line import SalesInvoiceLine
    from seeker_accounting.modules.sales.models.customer_receipt import CustomerReceipt
    from seeker_accounting.modules.sales.models.customer_receipt_allocation import CustomerReceiptAllocation
    from seeker_accounting.modules.purchases.models.purchase_bill import PurchaseBill
    from seeker_accounting.modules.purchases.models.purchase_bill_line import PurchaseBillLine
    from seeker_accounting.modules.purchases.models.supplier_payment import SupplierPayment
    from seeker_accounting.modules.purchases.models.supplier_payment_allocation import SupplierPaymentAllocation
    from seeker_accounting.modules.payroll.models.department import Department
    from seeker_accounting.modules.payroll.models.position import Position
    from seeker_accounting.modules.payroll.models.employee import Employee
    from seeker_accounting.modules.payroll.models.payroll_component import PayrollComponent
    from seeker_accounting.modules.payroll.models.employee_compensation_profile import EmployeeCompensationProfile
    from seeker_accounting.modules.contracts_projects.models.contract import Contract
    from seeker_accounting.modules.contracts_projects.models.project import Project
    from seeker_accounting.modules.contracts_projects.models.project_job import ProjectJob
    from seeker_accounting.modules.contracts_projects.models.project_cost_code import ProjectCostCode
    from seeker_accounting.modules.budgeting.models.project_budget_version import ProjectBudgetVersion
    from seeker_accounting.modules.budgeting.models.project_budget_line import ProjectBudgetLine
    from seeker_accounting.modules.fixed_assets.models.asset_category import AssetCategory
    from seeker_accounting.modules.fixed_assets.models.asset import Asset
    from seeker_accounting.modules.fixed_assets.models.asset_depreciation_run import AssetDepreciationRun
    from seeker_accounting.modules.fixed_assets.models.asset_depreciation_run_line import AssetDepreciationRunLine
    from seeker_accounting.modules.inventory.models.uom_category import UomCategory
    from seeker_accounting.modules.inventory.models.unit_of_measure import UnitOfMeasure
    from seeker_accounting.modules.inventory.models.item_category import ItemCategory
    from seeker_accounting.modules.inventory.models.inventory_location import InventoryLocation
    from seeker_accounting.modules.inventory.models.item import Item
    from seeker_accounting.modules.inventory.models.inventory_document import InventoryDocument
    from seeker_accounting.modules.inventory.models.inventory_document_line import InventoryDocumentLine
    from seeker_accounting.modules.inventory.models.inventory_cost_layer import InventoryCostLayer

    with reg.session_context.unit_of_work_factory() as uow:
        S = uow.session

        # ==================================================================
        # 4. USERS, ROLES, PERMISSIONS
        # ==================================================================
        print("\n[4/12] Creating users and role assignments...")

        # Fetch existing system roles
        roles = {r.code: r for r in S.query(Role).all()}

        # Create admin user
        admin_user = User(
            username="admin",
            display_name="System Administrator",
            email="admin@afritech-solutions.cm",
            password_hash=_hash("sysadmin"),
            must_change_password=False,
            is_active=True,
            created_at=NOW, updated_at=NOW,
        )
        S.add(admin_user)
        S.flush()
        ADMIN_ID = admin_user.id

        # Create role-based user accounts
        role_users = [
            ("fm_nkouam", "Marie Nkouam", "finance_manager", "fmanager1"),
            ("acct_tabi", "Joseph Tabi", "general_accountant", "accountant1"),
            ("ar_fon", "Grace Fon", "ar_officer", "arofficer1"),
            ("ap_ngwa", "Paul Ngwa", "ap_officer", "apofficer1"),
            ("tr_beyala", "Sylvie Beyala", "treasury_officer", "trofficer1"),
            ("audit_mbah", "Emmanuel Mbah", "auditor_read_only", "auditor01"),
        ]

        user_ids = {"admin": ADMIN_ID}
        for username, display_name, role_code, password in role_users:
            u = User(
                username=username,
                display_name=display_name,
                email=f"{username}@afritech-solutions.cm",
                password_hash=_hash(password),
                must_change_password=True,
                is_active=True,
                created_at=NOW, updated_at=NOW,
            )
            S.add(u)
            S.flush()
            user_ids[username] = u.id

            # Assign role
            S.add(UserRole(user_id=u.id, role_id=roles[role_code].id))
            # Grant company access
            S.add(UserCompanyAccess(
                user_id=u.id, company_id=CID,
                granted_by_user_id=ADMIN_ID,
                granted_at=NOW,
            ))

        # Admin gets company_admin role + company access
        S.add(UserRole(user_id=ADMIN_ID, role_id=roles["company_admin"].id))
        S.add(UserCompanyAccess(
            user_id=ADMIN_ID, company_id=CID,
            granted_by_user_id=ADMIN_ID,
            granted_at=NOW,
        ))
        S.flush()
        print(f"  OK — 7 users created (admin + 6 role accounts)")

        # ==================================================================
        # 5. REFERENCE DATA
        # ==================================================================
        print("\n[5/12] Creating reference data (tax codes, payment terms, sequences)...")

        # Tax codes
        vat_19 = TaxCode(
            company_id=CID, code="VAT19.25", name="VAT 19.25%",
            tax_type_code="VAT", calculation_method_code="PERCENTAGE",
            rate_percent=Decimal("19.25"), is_recoverable=True,
            effective_from=date(2024, 1, 1),
            is_active=True, created_at=NOW, updated_at=NOW,
        )
        vat_0 = TaxCode(
            company_id=CID, code="VAT0", name="VAT Exempt",
            tax_type_code="VAT", calculation_method_code="PERCENTAGE",
            rate_percent=Decimal("0"), is_recoverable=False,
            effective_from=date(2024, 1, 1),
            is_active=True, created_at=NOW, updated_at=NOW,
        )
        S.add_all([vat_19, vat_0])
        S.flush()

        # Payment terms
        pt_immediate = PaymentTerm(company_id=CID, code="IMMEDIATE", name="Immediate", days_due=0, is_active=True)
        pt_net15 = PaymentTerm(company_id=CID, code="NET15", name="Net 15", days_due=15, is_active=True)
        pt_net30 = PaymentTerm(company_id=CID, code="NET30", name="Net 30", days_due=30, is_active=True)
        pt_net60 = PaymentTerm(company_id=CID, code="NET60", name="Net 60", days_due=60, is_active=True)
        pt_net90 = PaymentTerm(company_id=CID, code="NET90", name="Net 90", days_due=90, is_active=True)
        S.add_all([pt_immediate, pt_net15, pt_net30, pt_net60, pt_net90])
        S.flush()

        # Document sequences
        seq_types = [
            ("journal_entry", "JE-", 6),
            ("SALES_INVOICE", "INV-", 6),
            ("CUSTOMER_RECEIPT", "REC-", 6),
            ("PURCHASE_BILL", "BILL-", 6),
            ("SUPPLIER_PAYMENT", "PAY-", 6),
            ("TREASURY_TRANSACTION", "TT-", 6),
            ("TREASURY_TRANSFER", "TF-", 6),
            ("INVENTORY_DOCUMENT", "INV-DOC-", 6),
            ("DEPRECIATION_RUN", "DEP-", 6),
        ]
        for doc_type, prefix, pad in seq_types:
            S.add(DocumentSequence(
                company_id=CID, document_type_code=doc_type,
                prefix=prefix, next_number=1, padding_width=pad,
                created_at=NOW, updated_at=NOW, is_active=True,
            ))
        S.flush()

        # Account role mappings
        role_mapping_data = [
            ("default_ar_control", "411"),
            ("default_ap_control", "401"),
            ("default_sales_revenue", "701"),
            ("default_purchase_expense", "601"),
            ("default_vat_output", "4431"),
            ("default_vat_input", "4451"),
            ("retained_earnings", "12"),
            ("default_salary_expense", "661"),
            ("default_salary_payable", "422"),
        ]
        for role_code, acct_code in role_mapping_data:
            try:
                aid = acct_id(acct_code)
                S.add(AccountRoleMapping(
                    company_id=CID, role_code=role_code, account_id=aid,
                    updated_at=NOW,
                ))
            except ValueError:
                print(f"  WARN: Account {acct_code} not found for role {role_code}")
        S.flush()
        print("  OK — tax codes, payment terms, sequences, role mappings")

        # ==================================================================
        # 6. FISCAL YEARS AND PERIODS
        # ==================================================================
        print("\n[6/12] Creating fiscal years and periods (2024-2026)...")

        fiscal_years = {}
        fiscal_periods = {}  # (year, month) -> period

        for yr in [2024, 2025, 2026]:
            fy_status = "CLOSED" if yr < 2026 else "OPEN"
            fy = FiscalYear(
                company_id=CID,
                year_code=str(yr),
                year_name=f"Fiscal Year {yr}",
                start_date=date(yr, 1, 1),
                end_date=date(yr, 12, 31),
                status_code=fy_status,
                is_active=True,
                created_at=NOW, updated_at=NOW,
            )
            S.add(fy)
            S.flush()
            fiscal_years[yr] = fy

            for m in range(1, 13):
                if m == 12:
                    end_d = date(yr, 12, 31)
                else:
                    end_d = date(yr, m + 1, 1) - timedelta(days=1)

                if yr < 2026:
                    p_status = "CLOSED"
                elif yr == 2026 and m <= 3:
                    p_status = "OPEN"
                elif yr == 2026 and m > 3:
                    p_status = "OPEN"
                else:
                    p_status = "OPEN"

                fp = FiscalPeriod(
                    company_id=CID,
                    fiscal_year_id=fy.id,
                    period_number=m,
                    period_code=f"{yr}-{m:02d}",
                    period_name=f"{date(yr, m, 1).strftime('%B')} {yr}",
                    start_date=date(yr, m, 1),
                    end_date=end_d,
                    status_code=p_status,
                    created_at=NOW, updated_at=NOW,
                )
                S.add(fp)
                S.flush()
                fiscal_periods[(yr, m)] = fp

        print(f"  OK — 3 fiscal years, 36 periods")

        # ==================================================================
        # 7. FINANCIAL ACCOUNTS
        # ==================================================================
        print("\n[7/12] Creating financial accounts...")

        fa_bank1 = FinancialAccount(
            company_id=CID, account_code="BNK-001", name="Afriland First Bank - Main",
            financial_account_type_code="bank", gl_account_id=acct_id("521"),
            bank_name="Afriland First Bank", bank_account_number="AF001-2024-00412",
            bank_branch="Douala Akwa", currency_code="XAF",
            is_active=True, created_at=NOW, updated_at=NOW,
        )
        fa_bank2 = FinancialAccount(
            company_id=CID, account_code="BNK-002", name="BICEC - Operations",
            financial_account_type_code="bank", gl_account_id=acct_id("521"),
            bank_name="BICEC", bank_account_number="BIC-2024-00098",
            bank_branch="Douala Bonanjo", currency_code="XAF",
            is_active=True, created_at=NOW, updated_at=NOW,
        )
        fa_cash = FinancialAccount(
            company_id=CID, account_code="CASH-001", name="Main Office Cash",
            financial_account_type_code="cash", gl_account_id=acct_id("571"),
            currency_code="XAF",
            is_active=True, created_at=NOW, updated_at=NOW,
        )
        fa_cash2 = FinancialAccount(
            company_id=CID, account_code="CASH-002", name="Petty Cash",
            financial_account_type_code="cash", gl_account_id=acct_id("571"),
            currency_code="XAF",
            is_active=True, created_at=NOW, updated_at=NOW,
        )
        S.add_all([fa_bank1, fa_bank2, fa_cash, fa_cash2])
        S.flush()
        print("  OK — 4 financial accounts (2 bank, 2 cash)")

        # ==================================================================
        # 8. THIRD PARTIES (CUSTOMERS + SUPPLIERS)
        # ==================================================================
        print("\n[8/12] Creating customers and suppliers...")

        # Customer groups
        cg_corp = CustomerGroup(company_id=CID, code="CORP", name="Corporate", is_active=True, created_at=NOW, updated_at=NOW)
        cg_govt = CustomerGroup(company_id=CID, code="GOVT", name="Government", is_active=True, created_at=NOW, updated_at=NOW)
        cg_sme = CustomerGroup(company_id=CID, code="SME", name="Small & Medium Business", is_active=True, created_at=NOW, updated_at=NOW)
        cg_ngo = CustomerGroup(company_id=CID, code="NGO", name="Non-Profit / NGO", is_active=True, created_at=NOW, updated_at=NOW)
        S.add_all([cg_corp, cg_govt, cg_sme, cg_ngo])
        S.flush()

        # Supplier groups
        sg_mat = SupplierGroup(company_id=CID, code="MAT", name="Materials & Equipment", is_active=True, created_at=NOW, updated_at=NOW)
        sg_srv = SupplierGroup(company_id=CID, code="SRV", name="Service Providers", is_active=True, created_at=NOW, updated_at=NOW)
        sg_sub = SupplierGroup(company_id=CID, code="SUB", name="Subcontractors", is_active=True, created_at=NOW, updated_at=NOW)
        sg_util = SupplierGroup(company_id=CID, code="UTIL", name="Utilities & Admin", is_active=True, created_at=NOW, updated_at=NOW)
        S.add_all([sg_mat, sg_srv, sg_sub, sg_util])
        S.flush()

        # 28 Customers
        customer_data = [
            ("C001", "CIMENCAM SA", cg_corp.id, "Douala"),
            ("C002", "Dangote Cement Cameroun", cg_corp.id, "Douala"),
            ("C003", "SODECOTON", cg_corp.id, "Garoua"),
            ("C004", "SONARA", cg_corp.id, "Limbe"),
            ("C005", "SABC Brasseries", cg_corp.id, "Douala"),
            ("C006", "MTN Cameroon", cg_corp.id, "Douala"),
            ("C007", "Orange Cameroun", cg_corp.id, "Douala"),
            ("C008", "CAMTEL", cg_govt.id, "Yaoundé"),
            ("C009", "Ministère des Travaux Publics", cg_govt.id, "Yaoundé"),
            ("C010", "Communauté Urbaine de Douala", cg_govt.id, "Douala"),
            ("C011", "Port Autonome de Douala", cg_govt.id, "Douala"),
            ("C012", "Université de Douala", cg_govt.id, "Douala"),
            ("C013", "ENEO Cameroon", cg_corp.id, "Douala"),
            ("C014", "CamWater", cg_govt.id, "Douala"),
            ("C015", "Tradex Cameroun", cg_corp.id, "Douala"),
            ("C016", "Express Union Finance", cg_sme.id, "Douala"),
            ("C017", "Société Générale Cameroun", cg_corp.id, "Douala"),
            ("C018", "BICEC Cameroun", cg_corp.id, "Douala"),
            ("C019", "Cabinet Conseil Etoundi", cg_sme.id, "Yaoundé"),
            ("C020", "Archi-Design Cameroun", cg_sme.id, "Douala"),
            ("C021", "Complexe Scolaire La Référence", cg_sme.id, "Douala"),
            ("C022", "Clinique de l'Aéroport", cg_sme.id, "Douala"),
            ("C023", "GIZ Cameroun", cg_ngo.id, "Yaoundé"),
            ("C024", "UNICEF Cameroon", cg_ngo.id, "Yaoundé"),
            ("C025", "World Bank - Cameroon Office", cg_ngo.id, "Yaoundé"),
            ("C026", "Mairie de Yaoundé III", cg_govt.id, "Yaoundé"),
            ("C027", "Neptune Oil & Gas", cg_corp.id, "Douala"),
            ("C028", "Cameroon Airlines Corporation", cg_corp.id, "Douala"),
        ]

        customers = {}
        for code, name, group_id, city in customer_data:
            c = Customer(
                company_id=CID, customer_code=code, display_name=name,
                customer_group_id=group_id, payment_term_id=pt_net30.id,
                city=city, country_code="CM", is_active=True,
                created_at=NOW, updated_at=NOW,
            )
            S.add(c)
            S.flush()
            customers[code] = c

        # 20 Suppliers
        supplier_data = [
            ("S001", "Quincaillerie Générale du Littoral", sg_mat.id, "Douala"),
            ("S002", "SOCAPALM Équipement", sg_mat.id, "Douala"),
            ("S003", "Cami-Toyota Cameroun", sg_mat.id, "Douala"),
            ("S004", "CFAO Motors", sg_mat.id, "Douala"),
            ("S005", "RAZEL Cameroun", sg_sub.id, "Douala"),
            ("S006", "Sogea-Satom Cameroun", sg_sub.id, "Douala"),
            ("S007", "Bolloré Transport & Logistics", sg_srv.id, "Douala"),
            ("S008", "DHL Cameroun", sg_srv.id, "Douala"),
            ("S009", "Tecno Mobile Cameroun", sg_mat.id, "Douala"),
            ("S010", "HP Cameroun (Distribué par CFAO)", sg_mat.id, "Douala"),
            ("S011", "Fournitures Bureau Express", sg_mat.id, "Douala"),
            ("S012", "ENEO (Électricité)", sg_util.id, "Douala"),
            ("S013", "CamWater (Eau)", sg_util.id, "Douala"),
            ("S014", "MTN Business Services", sg_srv.id, "Douala"),
            ("S015", "Assurances AXA Cameroun", sg_srv.id, "Douala"),
            ("S016", "Cabinet Comptable Fotso & Associés", sg_srv.id, "Douala"),
            ("S017", "BTP Matériaux SA", sg_mat.id, "Douala"),
            ("S018", "Location Engins Cameroun", sg_sub.id, "Douala"),
            ("S019", "Sécurité Gardiennage Plus", sg_srv.id, "Douala"),
            ("S020", "Nettoyage Professionnel SARL", sg_srv.id, "Douala"),
        ]

        suppliers = {}
        for code, name, group_id, city in supplier_data:
            s = Supplier(
                company_id=CID, supplier_code=code, display_name=name,
                supplier_group_id=group_id, payment_term_id=pt_net30.id,
                city=city, country_code="CM", is_active=True,
                created_at=NOW, updated_at=NOW,
            )
            S.add(s)
            S.flush()
            suppliers[code] = s

        print(f"  OK — 28 customers, 20 suppliers (48 third parties)")

        # ==================================================================
        # 9. CONTRACTS, PROJECTS, JOBS, COST CODES, BUDGETS
        # ==================================================================
        print("\n[9/12] Creating contracts, projects, jobs, cost codes, budgets...")

        # Cost codes (shared)
        cc_data = [
            ("LAB", "Labour", "labour"),
            ("MAT", "Materials", "materials"),
            ("SUB", "Subcontractor", "subcontract"),
            ("EQP", "Equipment", "equipment"),
            ("OVH", "Overhead", "overhead"),
            ("TRV", "Travel & Transport", "other"),
            ("DES", "Design & Engineering", "labour"),
            ("PMG", "Project Management", "labour"),
        ]
        cost_codes = {}
        for code, name, type_code in cc_data:
            cc = ProjectCostCode(
                company_id=CID, code=code, name=name,
                cost_code_type_code=type_code, is_active=True,
                created_at=NOW, updated_at=NOW,
            )
            S.add(cc)
            S.flush()
            cost_codes[code] = cc

        # 14 Contracts
        contract_data = [
            ("CTR-001", "CIMENCAM Plant Network Upgrade", "C001", "fixed_price", 85_000_000, "2024-03-01", "2025-06-30", "completed"),
            ("CTR-002", "Dangote Office Complex Construction", "C002", "fixed_price", 450_000_000, "2024-01-15", "2025-12-31", "active"),
            ("CTR-003", "SODECOTON IT Infrastructure", "C003", "fixed_price", 120_000_000, "2024-06-01", "2025-03-31", "completed"),
            ("CTR-004", "SONARA Pipeline Monitoring System", "C004", "time_and_materials", 200_000_000, "2024-09-01", "2026-06-30", "active"),
            ("CTR-005", "MTN Data Center Expansion", "C006", "fixed_price", 350_000_000, "2024-04-01", "2026-03-31", "active"),
            ("CTR-006", "Orange Office Renovation", "C007", "fixed_price", 95_000_000, "2025-01-01", "2025-09-30", "active"),
            ("CTR-007", "Ministère TP Road Survey", "C009", "time_and_materials", 180_000_000, "2024-07-01", "2026-01-31", "active"),
            ("CTR-008", "Port Autonome Warehouse System", "C011", "fixed_price", 275_000_000, "2025-03-01", "2026-12-31", "active"),
            ("CTR-009", "University Campus Network", "C012", "fixed_price", 65_000_000, "2025-06-01", "2026-03-31", "active"),
            ("CTR-010", "ENEO Smart Grid Phase 1", "C013", "time_and_materials", 500_000_000, "2024-02-01", "2026-12-31", "active"),
            ("CTR-011", "GIZ Water Supply Project", "C023", "fixed_price", 320_000_000, "2024-08-01", "2026-09-30", "active"),
            ("CTR-012", "UNICEF School IT Program", "C024", "fixed_price", 150_000_000, "2025-01-15", "2026-06-30", "active"),
            ("CTR-013", "World Bank Road Rehabilitation", "C025", "time_and_materials", 800_000_000, "2024-05-01", "2027-12-31", "active"),
            ("CTR-014", "Neptune Oil Facility Maintenance", "C027", "time_and_materials", 250_000_000, "2025-04-01", "2027-03-31", "active"),
        ]

        contracts = {}
        for ctr_num, title, cust_code, ctype, amount, start, end, status in contract_data:
            ct = Contract(
                company_id=CID, contract_number=ctr_num, contract_title=title,
                customer_id=customers[cust_code].id,
                contract_type_code=ctype, currency_code="XAF",
                base_contract_amount=Decimal(amount),
                start_date=date.fromisoformat(start),
                planned_end_date=date.fromisoformat(end),
                status_code=status,
                created_by_user_id=ADMIN_ID,
                created_at=NOW, updated_at=NOW,
            )
            S.add(ct)
            S.flush()
            contracts[ctr_num] = ct

        # 38 Projects (2-3 per contract + some standalone)
        project_defs = [
            ("P001", "CIMENCAM Network Design", "CTR-001", "C001", "internal", "2024-03-01", "2024-08-31", "completed"),
            ("P002", "CIMENCAM Network Installation", "CTR-001", "C001", "construction", "2024-06-01", "2025-06-30", "completed"),
            ("P003", "Dangote - Foundations & Structure", "CTR-002", "C002", "construction", "2024-01-15", "2024-12-31", "active"),
            ("P004", "Dangote - Electrical & Plumbing", "CTR-002", "C002", "construction", "2024-08-01", "2025-09-30", "active"),
            ("P005", "Dangote - Interior Finishing", "CTR-002", "C002", "construction", "2025-03-01", "2025-12-31", "active"),
            ("P006", "SODECOTON Server Room Setup", "CTR-003", "C003", "internal", "2024-06-01", "2024-12-31", "completed"),
            ("P007", "SODECOTON Network Cabling", "CTR-003", "C003", "construction", "2024-08-01", "2025-03-31", "completed"),
            ("P008", "SONARA Sensor Deployment", "CTR-004", "C004", "construction", "2024-09-01", "2025-12-31", "active"),
            ("P009", "SONARA Software Platform", "CTR-004", "C004", "internal", "2025-01-01", "2026-06-30", "active"),
            ("P010", "MTN DC - Civil Works", "CTR-005", "C006", "construction", "2024-04-01", "2025-03-31", "active"),
            ("P011", "MTN DC - Power & Cooling", "CTR-005", "C006", "construction", "2024-07-01", "2025-09-30", "active"),
            ("P012", "MTN DC - Rack & Cabling", "CTR-005", "C006", "construction", "2025-01-01", "2026-03-31", "active"),
            ("P013", "Orange Office Interior", "CTR-006", "C007", "construction", "2025-01-01", "2025-06-30", "active"),
            ("P014", "Orange IT Setup", "CTR-006", "C007", "internal", "2025-04-01", "2025-09-30", "active"),
            ("P015", "Road Survey - Phase 1", "CTR-007", "C009", "construction", "2024-07-01", "2025-06-30", "active"),
            ("P016", "Road Survey - Phase 2", "CTR-007", "C009", "construction", "2025-07-01", "2026-01-31", "active"),
            ("P017", "Port Warehouse Structure", "CTR-008", "C011", "construction", "2025-03-01", "2026-03-31", "active"),
            ("P018", "Port IT & Security", "CTR-008", "C011", "internal", "2025-06-01", "2026-12-31", "active"),
            ("P019", "University Network Phase 1", "CTR-009", "C012", "internal", "2025-06-01", "2025-12-31", "active"),
            ("P020", "University Network Phase 2", "CTR-009", "C012", "internal", "2026-01-01", "2026-03-31", "active"),
            ("P021", "ENEO Grid Sensors", "CTR-010", "C013", "construction", "2024-02-01", "2025-06-30", "active"),
            ("P022", "ENEO Grid Software", "CTR-010", "C013", "internal", "2024-06-01", "2026-06-30", "active"),
            ("P023", "ENEO Grid Deployment", "CTR-010", "C013", "construction", "2025-01-01", "2026-12-31", "active"),
            ("P024", "GIZ Water - Borehole Drilling", "CTR-011", "C023", "construction", "2024-08-01", "2025-12-31", "active"),
            ("P025", "GIZ Water - Pipe Network", "CTR-011", "C023", "construction", "2025-03-01", "2026-09-30", "active"),
            ("P026", "GIZ Water - Treatment Plant", "CTR-011", "C023", "construction", "2025-06-01", "2026-09-30", "active"),
            ("P027", "UNICEF School Labs - Phase 1", "CTR-012", "C024", "internal", "2025-01-15", "2025-12-31", "active"),
            ("P028", "UNICEF School Labs - Phase 2", "CTR-012", "C024", "internal", "2026-01-01", "2026-06-30", "active"),
            ("P029", "WB Road - Douala-Bafoussam Section", "CTR-013", "C025", "construction", "2024-05-01", "2026-06-30", "active"),
            ("P030", "WB Road - Bafoussam-Bamenda Section", "CTR-013", "C025", "construction", "2025-01-01", "2027-06-30", "active"),
            ("P031", "WB Road - Bridge Rehabilitation", "CTR-013", "C025", "construction", "2025-06-01", "2027-12-31", "active"),
            ("P032", "Neptune Facility - Electrical", "CTR-014", "C027", "construction", "2025-04-01", "2026-06-30", "active"),
            ("P033", "Neptune Facility - Plumbing", "CTR-014", "C027", "construction", "2025-04-01", "2026-09-30", "active"),
            ("P034", "Internal R&D - IoT Sensors", None, None, "internal", "2024-01-01", "2026-12-31", "active"),
            ("P035", "Internal - Office Renovation", None, None, "internal", "2025-06-01", "2025-12-31", "active"),
            ("P036", "SABC Brewery Automation", None, "C005", "construction", "2025-09-01", "2026-12-31", "active"),
            ("P037", "Tradex Fuel Station Tech", None, "C015", "internal", "2025-07-01", "2026-06-30", "active"),
            ("P038", "Express Union Branch IT", None, "C016", "internal", "2026-01-01", "2026-09-30", "active"),
        ]

        projects = {}
        for p_code, p_name, ctr_key, cust_code, ptype, start, end, status in project_defs:
            p = Project(
                company_id=CID, project_code=p_code, project_name=p_name,
                contract_id=contracts[ctr_key].id if ctr_key else None,
                customer_id=customers[cust_code].id if cust_code else None,
                project_type_code=ptype,
                currency_code="XAF",
                start_date=date.fromisoformat(start),
                planned_end_date=date.fromisoformat(end),
                status_code=status,
                created_by_user_id=ADMIN_ID,
                created_at=NOW, updated_at=NOW,
            )
            S.add(p)
            S.flush()
            projects[p_code] = p

        # Jobs: 2-4 per project for the first 20 projects
        jobs = {}
        job_counter = 0
        for p_code in list(projects.keys())[:20]:
            proj = projects[p_code]
            num_jobs = RNG.randint(2, 4)
            job_names = ["Planning & Design", "Procurement", "Execution", "Testing & Commissioning", "Handover"]
            for j in range(num_jobs):
                job_counter += 1
                jb = ProjectJob(
                    company_id=CID, project_id=proj.id,
                    job_code=f"J{job_counter:03d}",
                    job_name=job_names[j % len(job_names)],
                    sequence_number=j + 1,
                    status_code="active",
                    start_date=proj.start_date,
                    planned_end_date=proj.planned_end_date,
                    allow_direct_cost_posting=True,
                    created_at=NOW, updated_at=NOW,
                )
                S.add(jb)
                S.flush()
                jobs[f"{p_code}-{j}"] = jb

        # Budgets: one per project for first 20 projects
        for i, p_code in enumerate(list(projects.keys())[:20]):
            proj = projects[p_code]
            bv = ProjectBudgetVersion(
                company_id=CID, project_id=proj.id,
                version_number=1, version_name="Initial Budget",
                version_type_code="original",
                status_code="approved",
                budget_date=proj.start_date or date(2024, 1, 1),
                total_budget_amount=Decimal(RNG.randint(20, 200) * 1_000_000),
                approved_at=NOW, approved_by_user_id=ADMIN_ID,
                created_at=NOW, updated_at=NOW,
            )
            S.add(bv)
            S.flush()

            # Budget lines
            line_num = 0
            for cc_code in ["LAB", "MAT", "SUB", "EQP"]:
                line_num += 1
                S.add(ProjectBudgetLine(
                    project_budget_version_id=bv.id,
                    line_number=line_num,
                    project_cost_code_id=cost_codes[cc_code].id,
                    description=f"{cost_codes[cc_code].name} budget",
                    line_amount=Decimal(RNG.randint(5, 50) * 1_000_000),
                    created_at=NOW, updated_at=NOW,
                ))

        S.flush()
        print(f"  OK — 14 contracts, 38 projects, {job_counter} jobs, 8 cost codes, 20 budgets")

        # ==================================================================
        # 10. EMPLOYEES & PAYROLL
        # ==================================================================
        print("\n[10/12] Creating departments, positions, employees...")

        # Departments
        dept_data = [
            ("ENG", "Engineering"),
            ("CONST", "Construction"),
            ("FIN", "Finance & Admin"),
            ("IT", "Information Technology"),
            ("MGT", "Management"),
        ]
        departments = {}
        for code, name in dept_data:
            d = Department(company_id=CID, code=code, name=name, is_active=True, created_at=NOW, updated_at=NOW)
            S.add(d)
            S.flush()
            departments[code] = d

        # Positions
        pos_data = [
            ("CEO", "Chief Executive Officer"),
            ("CFO", "Chief Financial Officer"),
            ("CTO", "Chief Technology Officer"),
            ("PM", "Project Manager"),
            ("SE", "Senior Engineer"),
            ("ENG", "Engineer"),
            ("TECH", "Technician"),
            ("ACCT", "Accountant"),
            ("ADMIN", "Administrative Assistant"),
            ("FOREMAN", "Site Foreman"),
        ]
        positions = {}
        for code, name in pos_data:
            p = Position(company_id=CID, code=code, name=name, is_active=True, created_at=NOW, updated_at=NOW)
            S.add(p)
            S.flush()
            positions[code] = p

        # 17 Employees
        emp_data = [
            ("EMP001", "Jean-Pierre", "Kouam", "MGT", "CEO", date(2023, 7, 1), 3_500_000),
            ("EMP002", "Isabelle", "Ngo Biyong", "FIN", "CFO", date(2023, 7, 1), 2_800_000),
            ("EMP003", "Samuel", "Etundi", "IT", "CTO", date(2023, 7, 1), 2_800_000),
            ("EMP004", "Alphonse", "Tchinda", "ENG", "PM", date(2023, 8, 1), 1_800_000),
            ("EMP005", "Yvette", "Fouda", "ENG", "PM", date(2023, 9, 1), 1_800_000),
            ("EMP006", "Michel", "Mbarga", "ENG", "SE", date(2023, 10, 1), 1_500_000),
            ("EMP007", "Claudine", "Mfopou", "ENG", "SE", date(2024, 1, 15), 1_500_000),
            ("EMP008", "Patrick", "Nkwenti", "CONST", "FOREMAN", date(2024, 2, 1), 800_000),
            ("EMP009", "Brigitte", "Atemkeng", "CONST", "TECH", date(2024, 3, 1), 600_000),
            ("EMP010", "Denis", "Wambo", "CONST", "TECH", date(2024, 3, 1), 600_000),
            ("EMP011", "François", "Tchatchoua", "CONST", "TECH", date(2024, 4, 15), 550_000),
            ("EMP012", "Sylvie", "Kamdem", "FIN", "ACCT", date(2024, 1, 1), 1_200_000),
            ("EMP013", "Rosalie", "Ngono", "FIN", "ADMIN", date(2024, 6, 1), 450_000),
            ("EMP014", "Gilbert", "Njoya", "IT", "ENG", date(2024, 3, 15), 1_100_000),
            ("EMP015", "Martine", "Nana", "IT", "ENG", date(2024, 7, 1), 1_100_000),
            ("EMP016", "Thomas", "Messi", "CONST", "ENG", date(2025, 1, 15), 900_000),
            ("EMP017", "Alice", "Biloa", "FIN", "ADMIN", date(2025, 3, 1), 400_000),
        ]

        employees = {}
        for emp_num, first, last, dept, pos, hire, salary in emp_data:
            e = Employee(
                company_id=CID, employee_number=emp_num,
                display_name=f"{first} {last}",
                first_name=first, last_name=last,
                department_id=departments[dept].id,
                position_id=positions[pos].id,
                hire_date=hire,
                base_currency_code="XAF",
                is_active=True,
                created_at=NOW, updated_at=NOW,
            )
            S.add(e)
            S.flush()
            employees[emp_num] = (e, salary)

        S.flush()
        print(f"  OK — 5 departments, 10 positions, 17 employees")

        # ==================================================================
        # 11. FIXED ASSETS
        # ==================================================================
        print("\n[11/12] Creating asset categories and fixed assets...")

        # Asset categories
        cat_build = AssetCategory(
            company_id=CID, code="BLDG", name="Buildings & Installations",
            asset_account_id=acct_id("23"),
            accumulated_depreciation_account_id=acct_id("28"),
            depreciation_expense_account_id=acct_id("681"),
            default_useful_life_months=240, default_depreciation_method_code="straight_line",
            is_active=True, created_at=NOW, updated_at=NOW,
        )
        cat_equip = AssetCategory(
            company_id=CID, code="EQUIP", name="Equipment & Machinery",
            asset_account_id=acct_id("24"),
            accumulated_depreciation_account_id=acct_id("28"),
            depreciation_expense_account_id=acct_id("681"),
            default_useful_life_months=60, default_depreciation_method_code="straight_line",
            is_active=True, created_at=NOW, updated_at=NOW,
        )
        cat_vehicle = AssetCategory(
            company_id=CID, code="VEH", name="Vehicles",
            asset_account_id=acct_id("24"),
            accumulated_depreciation_account_id=acct_id("28"),
            depreciation_expense_account_id=acct_id("681"),
            default_useful_life_months=48, default_depreciation_method_code="straight_line",
            is_active=True, created_at=NOW, updated_at=NOW,
        )
        cat_it = AssetCategory(
            company_id=CID, code="IT", name="IT Equipment",
            asset_account_id=acct_id("24"),
            accumulated_depreciation_account_id=acct_id("28"),
            depreciation_expense_account_id=acct_id("681"),
            default_useful_life_months=36, default_depreciation_method_code="straight_line",
            is_active=True, created_at=NOW, updated_at=NOW,
        )
        cat_furn = AssetCategory(
            company_id=CID, code="FURN", name="Office Furniture",
            asset_account_id=acct_id("24"),
            accumulated_depreciation_account_id=acct_id("28"),
            depreciation_expense_account_id=acct_id("681"),
            default_useful_life_months=120, default_depreciation_method_code="straight_line",
            is_active=True, created_at=NOW, updated_at=NOW,
        )
        S.add_all([cat_build, cat_equip, cat_vehicle, cat_it, cat_furn])
        S.flush()

        asset_defs = [
            ("AST-001", "Office Building - Douala Akwa", cat_build, date(2023, 7, 15), 180_000_000, 20_000_000, 240, "active"),
            ("AST-002", "CAT Excavator 320D", cat_equip, date(2023, 8, 1), 75_000_000, 5_000_000, 60, "active"),
            ("AST-003", "Toyota Hilux Double Cab #1", cat_vehicle, date(2023, 9, 1), 22_000_000, 3_000_000, 48, "active"),
            ("AST-004", "Toyota Hilux Double Cab #2", cat_vehicle, date(2023, 9, 1), 22_000_000, 3_000_000, 48, "active"),
            ("AST-005", "Dell Server PowerEdge R740", cat_it, date(2023, 10, 1), 15_000_000, 500_000, 36, "active"),
            ("AST-006", "HP ProBook Laptops (10 units)", cat_it, date(2023, 10, 15), 12_500_000, 0, 36, "active"),
            ("AST-007", "Cement Mixer Truck", cat_equip, date(2024, 1, 15), 45_000_000, 3_000_000, 60, "active"),
            ("AST-008", "Mobile Crane 25T", cat_equip, date(2024, 3, 1), 95_000_000, 8_000_000, 60, "active"),
            ("AST-009", "Office Furniture Set - HQ", cat_furn, date(2024, 2, 1), 8_500_000, 0, 120, "active"),
            ("AST-010", "Generator 100KVA", cat_equip, date(2024, 6, 1), 18_000_000, 1_000_000, 60, "active"),
            ("AST-011", "Survey Equipment Set", cat_equip, date(2024, 8, 1), 25_000_000, 2_000_000, 60, "active"),
            ("AST-012", "Toyota Land Cruiser", cat_vehicle, date(2025, 1, 15), 35_000_000, 5_000_000, 48, "active"),
            ("AST-013", "Networking Equipment Rack", cat_it, date(2025, 3, 1), 8_000_000, 0, 36, "active"),
            ("AST-014", "Concrete Pump Truck", cat_equip, date(2025, 6, 1), 65_000_000, 5_000_000, 60, "active"),
        ]

        assets = {}
        for a_num, a_name, cat, acq_date, cost, salvage, life, status in asset_defs:
            a = Asset(
                company_id=CID, asset_number=a_num, asset_name=a_name,
                asset_category_id=cat.id,
                acquisition_date=acq_date, capitalization_date=acq_date,
                acquisition_cost=Decimal(cost),
                salvage_value=Decimal(salvage),
                useful_life_months=life,
                depreciation_method_code="straight_line",
                status_code=status,
                created_at=NOW, updated_at=NOW,
            )
            S.add(a)
            S.flush()
            assets[a_num] = a

        print(f"  OK — 5 asset categories, 14 fixed assets")

        # ==================================================================
        # 12. INVENTORY
        # ==================================================================
        print("\n[12a/12] Creating inventory items and UoM...")

        # UoM categories
        uom_cat_qty = UomCategory(company_id=CID, code="QTY", name="Quantity", is_active=True, created_at=NOW, updated_at=NOW)
        uom_cat_wt = UomCategory(company_id=CID, code="WT", name="Weight", is_active=True, created_at=NOW, updated_at=NOW)
        uom_cat_len = UomCategory(company_id=CID, code="LEN", name="Length", is_active=True, created_at=NOW, updated_at=NOW)
        uom_cat_vol = UomCategory(company_id=CID, code="VOL", name="Volume", is_active=True, created_at=NOW, updated_at=NOW)
        S.add_all([uom_cat_qty, uom_cat_wt, uom_cat_len, uom_cat_vol])
        S.flush()

        # UoMs
        uom_unit = UnitOfMeasure(company_id=CID, code="UNIT", name="Unit", category_id=uom_cat_qty.id, ratio_to_base=Decimal(1), is_active=True, created_at=NOW, updated_at=NOW)
        uom_kg = UnitOfMeasure(company_id=CID, code="KG", name="Kilogram", category_id=uom_cat_wt.id, ratio_to_base=Decimal(1), is_active=True, created_at=NOW, updated_at=NOW)
        uom_ton = UnitOfMeasure(company_id=CID, code="TON", name="Metric Ton", category_id=uom_cat_wt.id, ratio_to_base=Decimal(1000), is_active=True, created_at=NOW, updated_at=NOW)
        uom_m = UnitOfMeasure(company_id=CID, code="M", name="Metre", category_id=uom_cat_len.id, ratio_to_base=Decimal(1), is_active=True, created_at=NOW, updated_at=NOW)
        uom_l = UnitOfMeasure(company_id=CID, code="L", name="Litre", category_id=uom_cat_vol.id, ratio_to_base=Decimal(1), is_active=True, created_at=NOW, updated_at=NOW)
        uom_bag = UnitOfMeasure(company_id=CID, code="BAG", name="Bag (50kg)", category_id=uom_cat_wt.id, ratio_to_base=Decimal(50), is_active=True, created_at=NOW, updated_at=NOW)
        S.add_all([uom_unit, uom_kg, uom_ton, uom_m, uom_l, uom_bag])
        S.flush()

        # Item categories
        ic_const = ItemCategory(company_id=CID, code="CONST", name="Construction Materials", is_active=True, created_at=NOW, updated_at=NOW)
        ic_it = ItemCategory(company_id=CID, code="IT", name="IT Supplies", is_active=True, created_at=NOW, updated_at=NOW)
        ic_office = ItemCategory(company_id=CID, code="OFFICE", name="Office Supplies", is_active=True, created_at=NOW, updated_at=NOW)
        ic_fuel = ItemCategory(company_id=CID, code="FUEL", name="Fuel & Lubricants", is_active=True, created_at=NOW, updated_at=NOW)
        S.add_all([ic_const, ic_it, ic_office, ic_fuel])
        S.flush()

        # Inventory locations
        loc_main = InventoryLocation(company_id=CID, code="MAIN", name="Main Warehouse - Douala", is_active=True, created_at=NOW, updated_at=NOW)
        loc_site = InventoryLocation(company_id=CID, code="SITE", name="Construction Site Storage", is_active=True, created_at=NOW, updated_at=NOW)
        S.add_all([loc_main, loc_site])
        S.flush()

        # Items
        item_defs = [
            ("ITM-001", "Portland Cement CEM II", "stock", ic_const, uom_bag, 4_500, acct_id("31"), acct_id("601"), acct_id("601"), acct_id("701")),
            ("ITM-002", "Iron Rods 12mm", "stock", ic_const, uom_ton, 550_000, acct_id("31"), acct_id("601"), acct_id("601"), acct_id("701")),
            ("ITM-003", "River Sand", "stock", ic_const, uom_ton, 15_000, acct_id("31"), acct_id("601"), acct_id("601"), acct_id("701")),
            ("ITM-004", "Granite Gravel 20mm", "stock", ic_const, uom_ton, 25_000, acct_id("31"), acct_id("601"), acct_id("601"), acct_id("701")),
            ("ITM-005", "Network Cable CAT6 (305m)", "stock", ic_it, uom_unit, 85_000, acct_id("31"), acct_id("601"), acct_id("601"), acct_id("701")),
            ("ITM-006", "Cisco Switch 48-Port", "stock", ic_it, uom_unit, 450_000, acct_id("31"), acct_id("601"), acct_id("601"), acct_id("701")),
            ("ITM-007", "Printer Paper A4 (Ream)", "stock", ic_office, uom_unit, 3_500, acct_id("31"), acct_id("601"), acct_id("601"), acct_id("701")),
            ("ITM-008", "Diesel Fuel", "stock", ic_fuel, uom_l, 750, acct_id("31"), acct_id("601"), acct_id("601"), acct_id("701")),
            ("ITM-009", "PVC Pipes 110mm (6m)", "stock", ic_const, uom_unit, 12_000, acct_id("31"), acct_id("601"), acct_id("601"), acct_id("701")),
            ("ITM-010", "Electrical Cable 2.5mm²", "stock", ic_const, uom_m, 350, acct_id("31"), acct_id("601"), acct_id("601"), acct_id("701")),
            ("ITM-011", "Engineering Consultancy", "service", ic_it, uom_unit, 0, None, acct_id("602"), acct_id("602"), acct_id("706")),
            ("ITM-012", "Site Labour (per day)", "service", ic_const, uom_unit, 0, None, acct_id("602"), acct_id("602"), acct_id("706")),
        ]

        items = {}
        for i_code, i_name, i_type, cat, uom, cost, inv_acct, cogs_acct, exp_acct, rev_acct in item_defs:
            itm = Item(
                company_id=CID, item_code=i_code, item_name=i_name,
                item_type_code=i_type,
                unit_of_measure_code=uom.code,
                unit_of_measure_id=uom.id,
                item_category_id=cat.id,
                inventory_cost_method_code="weighted_average" if i_type == "stock" else None,
                inventory_account_id=inv_acct,
                cogs_account_id=cogs_acct,
                expense_account_id=exp_acct,
                revenue_account_id=rev_acct,
                is_active=True,
                created_at=NOW, updated_at=NOW,
            )
            S.add(itm)
            S.flush()
            items[i_code] = (itm, cost)

        print(f"  OK — 12 items, 4 categories, 6 UoMs, 2 locations")

        # ==================================================================
        # 12b. JOURNAL ENTRIES (the big transaction volume)
        # ==================================================================
        print("\n[12b/12] Creating ~720 journal entries across 3 years...")

        je_counter = 0
        si_counter = 0
        pb_counter = 0
        cr_counter = 0
        sp_counter = 0
        inv_doc_counter = 0

        def _make_je(entry_date: date, jtype: str, desc: str, lines: list[tuple],
                     source_module: str | None = None, source_doc_type: str | None = None,
                     source_doc_id: int | None = None) -> JournalEntry:
            """Create a posted JE. Each line tuple: (account_id, debit, credit[, project_id, job_id, cost_code_id])."""
            nonlocal je_counter
            je_counter += 1
            yr = entry_date.year
            m = entry_date.month
            fp = fiscal_periods.get((yr, m))
            if not fp:
                raise ValueError(f"No fiscal period for {yr}-{m:02d}")

            je = JournalEntry(
                company_id=CID,
                fiscal_period_id=fp.id,
                entry_number=f"JE-{je_counter:06d}",
                entry_date=entry_date,
                transaction_date=entry_date,
                journal_type_code=jtype,
                description=desc,
                source_module_code=source_module,
                source_document_type=source_doc_type,
                source_document_id=source_doc_id,
                status_code="POSTED",
                posted_at=datetime(entry_date.year, entry_date.month, entry_date.day, 12, 0, 0),
                posted_by_user_id=ADMIN_ID,
                created_by_user_id=ADMIN_ID,
                created_at=NOW, updated_at=NOW,
            )
            S.add(je)
            S.flush()

            for line_num, line_data in enumerate(lines, start=1):
                account_id_val, debit, credit = line_data[0], line_data[1], line_data[2]
                proj_id = line_data[3] if len(line_data) > 3 else None
                job_id = line_data[4] if len(line_data) > 4 else None
                cc_id = line_data[5] if len(line_data) > 5 else None
                S.add(JournalEntryLine(
                    journal_entry_id=je.id,
                    line_number=line_num,
                    account_id=account_id_val,
                    line_description=desc,
                    debit_amount=debit,
                    credit_amount=credit,
                    project_id=proj_id,
                    project_job_id=job_id,
                    project_cost_code_id=cc_id,
                    created_at=NOW, updated_at=NOW,
                ))
            S.flush()
            return je

        # --- OPENING BALANCES (Jan 1, 2024) ---
        # Capital contribution
        _make_je(date(2024, 1, 1), "general", "Opening capital contribution", [
            (acct_id("521"), Decimal(500_000_000), Decimal(0)),
            (acct_id("101"), Decimal(0), Decimal(500_000_000)),
        ])

        # Initial building capitalization
        _make_je(date(2024, 1, 1), "general", "Capitalize office building", [
            (acct_id("23"), Decimal(180_000_000), Decimal(0)),
            (acct_id("521"), Decimal(0), Decimal(180_000_000)),
        ])

        # Initial equipment
        _make_je(date(2024, 1, 1), "general", "Initial equipment purchases", [
            (acct_id("24"), Decimal(147_500_000), Decimal(0)),
            (acct_id("521"), Decimal(0), Decimal(147_500_000)),
        ])

        # --- Monthly recurring transactions ---
        customer_codes = list(customers.keys())
        supplier_codes = list(suppliers.keys())

        # Revenue accounts for different service types
        rev_service = acct_id("706")   # Services rendered
        rev_goods = acct_id("701")     # Sale of goods
        exp_purchases = acct_id("601") # Purchases
        exp_services = acct_id("602")  # External services
        exp_rent = acct_id("6222")    # Rent of buildings
        exp_insurance = acct_id("625")  # Insurance premiums
        exp_telecom = acct_id("628")   # Telecom
        exp_salary = acct_id("661")    # Salaries
        exp_social = acct_id("664")    # Social charges
        ar_control = acct_id("411")    # Customers
        ap_control = acct_id("401")    # Suppliers
        bank_acct = acct_id("521")     # Bank
        cash_acct = acct_id("571")     # Cash
        vat_output = acct_id("4431")   # VAT output
        vat_input = acct_id("4451")    # VAT input

        # Generate transactions month by month for 2024, 2025, and Q1 2026
        months = []
        for yr in [2024, 2025]:
            for m in range(1, 13):
                months.append((yr, m))
        for m in range(1, 4):  # Jan-Mar 2026
            months.append((2026, m))

        total_revenue = Decimal(0)
        total_expenses = Decimal(0)

        for yr, m in months:
            month_start = date(yr, m, 1)
            if m == 12:
                month_end = date(yr, 12, 28)
            else:
                month_end = date(yr, m + 1, 1) - timedelta(days=1)

            # Scale transactions: business grows over time
            if yr == 2024 and m <= 6:
                scale = 0.6
            elif yr == 2024:
                scale = 0.8
            elif yr == 2025 and m <= 6:
                scale = 1.0
            elif yr == 2025:
                scale = 1.2
            else:
                scale = 1.3

            # --- Sales Invoices (5-9 per month) ---
            num_invoices = int(RNG.randint(5, 9) * scale)
            for _ in range(num_invoices):
                inv_date = date(yr, m, RNG.randint(1, min(28, month_end.day)))
                cust_code = RNG.choice(customer_codes)
                base_amount = Decimal(RNG.randint(2, 45) * 1_000_000)
                tax = (base_amount * Decimal("19.25") / 100).quantize(Decimal("1"))
                total = base_amount + tax

                si_counter += 1
                si = SalesInvoice(
                    company_id=CID,
                    invoice_number=f"INV-{si_counter:06d}",
                    customer_id=customers[cust_code].id,
                    invoice_date=inv_date,
                    due_date=inv_date + timedelta(days=30),
                    currency_code="XAF",
                    status_code="posted",
                    payment_status_code="unpaid",
                    subtotal_amount=base_amount,
                    tax_amount=tax,
                    total_amount=total,
                    posted_by_user_id=ADMIN_ID,
                    posted_at=datetime(inv_date.year, inv_date.month, inv_date.day, 12, 0, 0),
                    created_at=NOW, updated_at=NOW,
                )
                S.add(si)
                S.flush()

                S.add(SalesInvoiceLine(
                    sales_invoice_id=si.id, line_number=1,
                    description=f"Professional services - {cust_code}",
                    quantity=Decimal(1), unit_price=base_amount,
                    tax_code_id=vat_19.id,
                    revenue_account_id=rev_service,
                    line_subtotal_amount=base_amount,
                    line_tax_amount=tax,
                    line_total_amount=total,
                    created_at=NOW, updated_at=NOW,
                ))
                S.flush()

                # Journal entry for the invoice
                je = _make_je(inv_date, "sales", f"Sales invoice INV-{si_counter:06d} - {cust_code}", [
                    (ar_control, total, Decimal(0)),
                    (rev_service, Decimal(0), base_amount),
                    (vat_output, Decimal(0), tax),
                ], source_module="sales", source_doc_type="SALES_INVOICE", source_doc_id=si.id)
                si.posted_journal_entry_id = je.id
                total_revenue += base_amount

            # --- Customer Receipts (4-7 per month, lagging invoices) ---
            num_receipts = int(RNG.randint(4, 7) * scale)
            for _ in range(num_receipts):
                rec_date = date(yr, m, RNG.randint(5, min(28, month_end.day)))
                cust_code = RNG.choice(customer_codes)
                amount = Decimal(RNG.randint(2, 40) * 1_000_000)

                cr_counter += 1
                cr = CustomerReceipt(
                    company_id=CID,
                    receipt_number=f"REC-{cr_counter:06d}",
                    customer_id=customers[cust_code].id,
                    financial_account_id=fa_bank1.id,
                    receipt_date=rec_date,
                    currency_code="XAF",
                    amount_received=amount,
                    status_code="posted",
                    posted_by_user_id=ADMIN_ID,
                    posted_at=datetime(rec_date.year, rec_date.month, rec_date.day, 12, 0, 0),
                    created_at=NOW, updated_at=NOW,
                )
                S.add(cr)
                S.flush()

                je = _make_je(rec_date, "receipt", f"Customer receipt REC-{cr_counter:06d}", [
                    (bank_acct, amount, Decimal(0)),
                    (ar_control, Decimal(0), amount),
                ], source_module="sales", source_doc_type="CUSTOMER_RECEIPT", source_doc_id=cr.id)
                cr.posted_journal_entry_id = je.id

            # --- Purchase Bills (4-7 per month) ---
            num_bills = int(RNG.randint(4, 7) * scale)
            for _ in range(num_bills):
                bill_date = date(yr, m, RNG.randint(1, min(28, month_end.day)))
                supp_code = RNG.choice(supplier_codes)
                base_amount = Decimal(RNG.randint(1, 25) * 1_000_000)
                tax = (base_amount * Decimal("19.25") / 100).quantize(Decimal("1"))
                total = base_amount + tax

                pb_counter += 1
                pb = PurchaseBill(
                    company_id=CID,
                    bill_number=f"BILL-{pb_counter:06d}",
                    supplier_id=suppliers[supp_code].id,
                    bill_date=bill_date,
                    due_date=bill_date + timedelta(days=30),
                    currency_code="XAF",
                    status_code="posted",
                    payment_status_code="unpaid",
                    subtotal_amount=base_amount,
                    tax_amount=tax,
                    total_amount=total,
                    posted_by_user_id=ADMIN_ID,
                    posted_at=datetime(bill_date.year, bill_date.month, bill_date.day, 12, 0, 0),
                    created_at=NOW, updated_at=NOW,
                )
                S.add(pb)
                S.flush()

                # Assign expense account based on supplier group
                sg = suppliers[supp_code].supplier_group_id
                if sg == sg_mat.id:
                    exp_acct_id = exp_purchases
                elif sg == sg_sub.id:
                    exp_acct_id = exp_services
                elif sg == sg_util.id:
                    exp_acct_id = exp_telecom
                else:
                    exp_acct_id = exp_services

                S.add(PurchaseBillLine(
                    purchase_bill_id=pb.id, line_number=1,
                    description=f"Purchase from {supp_code}",
                    quantity=Decimal(1), unit_cost=base_amount,
                    expense_account_id=exp_acct_id,
                    tax_code_id=vat_19.id,
                    line_subtotal_amount=base_amount,
                    line_tax_amount=tax,
                    line_total_amount=total,
                    created_at=NOW, updated_at=NOW,
                ))
                S.flush()

                je = _make_je(bill_date, "purchase", f"Purchase bill BILL-{pb_counter:06d} - {supp_code}", [
                    (exp_acct_id, base_amount, Decimal(0)),
                    (vat_input, tax, Decimal(0)),
                    (ap_control, Decimal(0), total),
                ], source_module="purchases", source_doc_type="PURCHASE_BILL", source_doc_id=pb.id)
                pb.posted_journal_entry_id = je.id
                total_expenses += base_amount

            # --- Supplier Payments (3-6 per month) ---
            num_payments = int(RNG.randint(3, 6) * scale)
            for _ in range(num_payments):
                pay_date = date(yr, m, RNG.randint(5, min(28, month_end.day)))
                supp_code = RNG.choice(supplier_codes)
                amount = Decimal(RNG.randint(1, 20) * 1_000_000)

                sp_counter += 1
                sp = SupplierPayment(
                    company_id=CID,
                    payment_number=f"PAY-{sp_counter:06d}",
                    supplier_id=suppliers[supp_code].id,
                    financial_account_id=fa_bank1.id,
                    payment_date=pay_date,
                    currency_code="XAF",
                    amount_paid=amount,
                    status_code="posted",
                    posted_by_user_id=ADMIN_ID,
                    posted_at=datetime(pay_date.year, pay_date.month, pay_date.day, 12, 0, 0),
                    created_at=NOW, updated_at=NOW,
                )
                S.add(sp)
                S.flush()

                je = _make_je(pay_date, "payment", f"Supplier payment PAY-{sp_counter:06d}", [
                    (ap_control, amount, Decimal(0)),
                    (bank_acct, Decimal(0), amount),
                ], source_module="purchases", source_doc_type="SUPPLIER_PAYMENT", source_doc_id=sp.id)
                sp.posted_journal_entry_id = je.id

            # --- Payroll Journal (monthly salary accrual) ---
            active_emps = [(e, sal) for emp_num, (e, sal) in employees.items()
                           if e.hire_date <= month_end and (e.termination_date is None or e.termination_date >= month_start)]
            if active_emps:
                total_salary = sum(sal for _, sal in active_emps)
                social_charges = int(total_salary * 0.185)  # ~18.5% employer contribution

                _make_je(date(yr, m, min(28, month_end.day)), "payroll", f"Payroll - {date(yr, m, 1).strftime('%B')} {yr}", [
                    (exp_salary, Decimal(total_salary), Decimal(0)),
                    (exp_social, Decimal(social_charges), Decimal(0)),
                    (acct_id("422"), Decimal(0), Decimal(total_salary)),
                    (acct_id("431"), Decimal(0), Decimal(social_charges)),
                ], source_module="payroll")

                # Salary payment
                _make_je(date(yr, m, min(28, month_end.day)), "payment", f"Salary payment - {date(yr, m, 1).strftime('%B')} {yr}", [
                    (acct_id("422"), Decimal(total_salary), Decimal(0)),
                    (bank_acct, Decimal(0), Decimal(total_salary)),
                ])

                total_expenses += Decimal(total_salary + social_charges)

            # --- Monthly rent ---
            rent_amount = Decimal(2_500_000)
            _make_je(date(yr, m, 1), "general", f"Office rent - {date(yr, m, 1).strftime('%B')} {yr}", [
                (exp_rent, rent_amount, Decimal(0)),
                (bank_acct, Decimal(0), rent_amount),
            ])
            total_expenses += rent_amount

            # --- Utilities ---
            util_amount = Decimal(RNG.randint(300, 800) * 1000)
            _make_je(date(yr, m, 15), "general", f"Utilities - {date(yr, m, 1).strftime('%B')} {yr}", [
                (exp_telecom, util_amount, Decimal(0)),
                (bank_acct, Decimal(0), util_amount),
            ])
            total_expenses += util_amount

            # --- Quarterly depreciation entries ---
            if m in [3, 6, 9, 12]:
                # Calculate depreciation for all active assets
                total_dep = Decimal(0)
                for a_num, asset in assets.items():
                    if asset.acquisition_date <= month_end:
                        monthly_dep = (asset.acquisition_cost - (asset.salvage_value or 0)) / asset.useful_life_months
                        quarterly_dep = (monthly_dep * 3).quantize(Decimal("1"))
                        total_dep += quarterly_dep

                if total_dep > 0:
                    _make_je(month_end, "depreciation", f"Quarterly depreciation Q{(m-1)//3+1} {yr}", [
                        (acct_id("681"), total_dep, Decimal(0)),
                        (acct_id("28"), Decimal(0), total_dep),
                    ])
                    total_expenses += total_dep

            # --- Inventory transactions (every other month for variety) ---
            if m % 2 == 1:
                # Stock receipt
                inv_doc_counter += 1
                doc_date = date(yr, m, 10)
                stock_items = [("ITM-001", 200, 4_500), ("ITM-002", 5, 550_000), ("ITM-008", 500, 750)]
                total_val = Decimal(sum(q * c for _, q, c in stock_items))

                inv_doc = InventoryDocument(
                    company_id=CID,
                    document_number=f"INV-DOC-{inv_doc_counter:06d}",
                    document_type_code="receipt",
                    document_date=doc_date,
                    status_code="posted",
                    location_id=loc_main.id,
                    total_value=total_val,
                    posted_by_user_id=ADMIN_ID,
                    posted_at=datetime(doc_date.year, doc_date.month, doc_date.day, 12, 0, 0),
                    created_at=NOW, updated_at=NOW,
                )
                S.add(inv_doc)
                S.flush()

                line_num = 0
                for item_code, qty, unit_cost_val in stock_items:
                    line_num += 1
                    itm, _ = items[item_code]
                    line_amt = Decimal(qty * unit_cost_val)
                    idl = InventoryDocumentLine(
                        inventory_document_id=inv_doc.id,
                        line_number=line_num,
                        item_id=itm.id,
                        quantity=Decimal(qty),
                        unit_cost=Decimal(unit_cost_val),
                        line_amount=line_amt,
                        counterparty_account_id=exp_purchases,
                        created_at=NOW,
                    )
                    S.add(idl)
                    S.flush()

                    # Cost layer
                    S.add(InventoryCostLayer(
                        company_id=CID,
                        item_id=itm.id,
                        inventory_document_line_id=idl.id,
                        layer_date=doc_date,
                        quantity_in=Decimal(qty),
                        quantity_remaining=Decimal(int(qty * 0.7)),
                        unit_cost=Decimal(unit_cost_val),
                        created_at=NOW,
                    ))

                je = _make_je(doc_date, "inventory", f"Stock receipt INV-DOC-{inv_doc_counter:06d}", [
                    (acct_id("31"), total_val, Decimal(0)),
                    (exp_purchases, Decimal(0), total_val),
                ], source_module="inventory", source_doc_type="INVENTORY_DOCUMENT", source_doc_id=inv_doc.id)
                inv_doc.posted_journal_entry_id = je.id

            # Flush every month
            S.flush()

        # --- Additional one-off journal entries for variety ---
        # Insurance payment (annual)
        _make_je(date(2024, 1, 15), "general", "Annual insurance premium 2024", [
            (exp_insurance, Decimal(8_500_000), Decimal(0)),
            (bank_acct, Decimal(0), Decimal(8_500_000)),
        ])
        _make_je(date(2025, 1, 15), "general", "Annual insurance premium 2025", [
            (exp_insurance, Decimal(9_200_000), Decimal(0)),
            (bank_acct, Decimal(0), Decimal(9_200_000)),
        ])
        _make_je(date(2026, 1, 15), "general", "Annual insurance premium 2026", [
            (exp_insurance, Decimal(9_800_000), Decimal(0)),
            (bank_acct, Decimal(0), Decimal(9_800_000)),
        ])

        # Loan drawdown
        _make_je(date(2024, 3, 1), "general", "Bank loan drawdown - equipment financing", [
            (bank_acct, Decimal(150_000_000), Decimal(0)),
            (acct_id("162"), Decimal(0), Decimal(150_000_000)),
        ])

        # Loan repayments (quarterly)
        for yr in [2024, 2025, 2026]:
            for q_month in [3, 6, 9, 12]:
                if yr == 2026 and q_month > 3:
                    break
                repay_date = date(yr, q_month, 25)
                principal = Decimal(6_250_000)
                interest = Decimal(1_875_000)
                _make_je(repay_date, "general", f"Loan repayment Q{(q_month-1)//3+1} {yr}", [
                    (acct_id("162"), principal, Decimal(0)),
                    (acct_id("671"), interest, Decimal(0)),
                    (bank_acct, Decimal(0), principal + interest),
                ])

        # Tax payments (VAT settlement quarterly)
        for yr in [2024, 2025, 2026]:
            for q_month in [3, 6, 9, 12]:
                if yr == 2026 and q_month > 3:
                    break
                tax_date = date(yr, q_month, 20)
                net_vat = Decimal(RNG.randint(5, 15) * 1_000_000)
                _make_je(tax_date, "general", f"VAT payment Q{(q_month-1)//3+1} {yr}", [
                    (vat_output, net_vat, Decimal(0)),
                    (vat_input, Decimal(0), Decimal(int(net_vat * Decimal("0.6")))),
                    (bank_acct, Decimal(0), net_vat - Decimal(int(net_vat * Decimal("0.6")))),
                ])

        # Dividend payment (end of year)
        _make_je(date(2025, 6, 30), "general", "Dividend distribution FY2024", [
            (acct_id("121"), Decimal(50_000_000), Decimal(0)),
            (bank_acct, Decimal(0), Decimal(50_000_000)),
        ])

        # Additional business transactions for volume
        # Petty cash replenishments (monthly)
        for yr in [2024, 2025, 2026]:
            end_m = 12 if yr < 2026 else 3
            for m in range(1, end_m + 1):
                amt = Decimal(RNG.randint(50, 200) * 1000)
                _make_je(date(yr, m, 5), "general", f"Petty cash replenishment {yr}-{m:02d}", [
                    (cash_acct, amt, Decimal(0)),
                    (bank_acct, Decimal(0), amt),
                ])

        # Equipment maintenance and repairs (bi-monthly)
        for yr in [2024, 2025, 2026]:
            end_m = 12 if yr < 2026 else 3
            for m in range(1, end_m + 1, 2):
                amt = Decimal(RNG.randint(500, 3000) * 1000)
                _make_je(date(yr, m, 20), "general", f"Equipment maintenance {yr}-{m:02d}", [
                    (acct_id("624"), amt, Decimal(0)),
                    (bank_acct, Decimal(0), amt),
                ])

        # Professional fees (quarterly - audit, legal)
        for yr in [2024, 2025, 2026]:
            for q_month in [3, 6, 9, 12]:
                if yr == 2026 and q_month > 3:
                    break
                amt = Decimal(RNG.randint(2, 8) * 1_000_000)
                _make_je(date(yr, q_month, 15), "general", f"Professional fees Q{(q_month-1)//3+1} {yr}", [
                    (acct_id("632"), amt, Decimal(0)),
                    (ap_control, Decimal(0), amt),
                ])

        S.flush()

        # Update document sequence counters
        seq_updates = {
            "journal_entry": je_counter + 1,
            "SALES_INVOICE": si_counter + 1,
            "CUSTOMER_RECEIPT": cr_counter + 1,
            "PURCHASE_BILL": pb_counter + 1,
            "SUPPLIER_PAYMENT": sp_counter + 1,
            "INVENTORY_DOCUMENT": inv_doc_counter + 1,
        }
        for doc_type, next_num in seq_updates.items():
            S.execute(
                text("UPDATE document_sequences SET next_number = :n WHERE company_id = :c AND document_type_code = :d"),
                {"n": next_num, "c": CID, "d": doc_type},
            )

        S.flush()

        print(f"  OK — {je_counter} journal entries created")
        print(f"       {si_counter} sales invoices")
        print(f"       {cr_counter} customer receipts")
        print(f"       {pb_counter} purchase bills")
        print(f"       {sp_counter} supplier payments")
        print(f"       {inv_doc_counter} inventory documents")

        # ==================================================================
        # COMMIT
        # ==================================================================
        print("\n  Committing all data...")
        uow.commit()

    # ==================================================================
    # SUMMARY
    # ==================================================================
    print("\n" + "=" * 70)
    print("  DEMO ORGANISATION SEEDED SUCCESSFULLY")
    print("=" * 70)
    print(f"""
  Company:          Afritech Solutions SARL (ID={CID})
  Country:          Cameroon (CM) / XAF
  Fiscal Years:     2024 (closed), 2025 (closed), 2026 (open)
  
  Users:
    admin / sysadmin         — Company Administrator
    fm_nkouam / fmanager1    — Finance Manager
    acct_tabi / accountant1  — General Accountant
    ar_fon / arofficer1      — AR Officer
    ap_ngwa / apofficer1     — AP Officer
    tr_beyala / trofficer1   — Treasury Officer
    audit_mbah / auditor01   — Auditor (Read Only)
  
  Third Parties:    28 customers, 20 suppliers
  Contracts:        14
  Projects:         38 (with jobs, cost codes, budgets)
  Employees:        17 across 5 departments
  Fixed Assets:     14 (various acquisition dates since mid-2023)
  Inventory Items:  12 (10 stock + 2 service)
  Financial Accts:  4 (2 bank + 2 cash)
  
  Journal Entries:  {je_counter}
  Sales Invoices:   {si_counter}
  Customer Receipts:{cr_counter}
  Purchase Bills:   {pb_counter}
  Supplier Payments:{sp_counter}
  Inventory Docs:   {inv_doc_counter}
""")


if __name__ == "__main__":
    main()
