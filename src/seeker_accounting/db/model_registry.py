from __future__ import annotations

from seeker_accounting.db.base import Base
from seeker_accounting.modules.accounting.chart_of_accounts.models.account import Account
from seeker_accounting.modules.accounting.fiscal_periods.models.fiscal_period import FiscalPeriod
from seeker_accounting.modules.accounting.fiscal_periods.models.fiscal_year import FiscalYear
from seeker_accounting.modules.accounting.journals.models.journal_entry import JournalEntry
from seeker_accounting.modules.accounting.journals.models.journal_entry_line import JournalEntryLine
from seeker_accounting.modules.accounting.reference_data.models.account_class import AccountClass
from seeker_accounting.modules.accounting.reference_data.models.account_role_mapping import AccountRoleMapping
from seeker_accounting.modules.accounting.reference_data.models.account_type import AccountType
from seeker_accounting.modules.accounting.reference_data.models.country import Country
from seeker_accounting.modules.accounting.reference_data.models.currency import Currency
from seeker_accounting.modules.accounting.reference_data.models.document_sequence import DocumentSequence
from seeker_accounting.modules.accounting.reference_data.models.payment_term import PaymentTerm
from seeker_accounting.modules.accounting.reference_data.models.tax_code import TaxCode
from seeker_accounting.modules.accounting.reference_data.models.tax_code_account_mapping import (
    TaxCodeAccountMapping,
)
from seeker_accounting.modules.reporting.models.ias_income_statement_mapping import (
    IasIncomeStatementMapping,
)
from seeker_accounting.modules.reporting.models.ias_income_statement_section import (
    IasIncomeStatementSection,
)
from seeker_accounting.modules.reporting.models.ias_income_statement_template import (
    IasIncomeStatementTemplate,
)
from seeker_accounting.modules.reporting.models.ias_income_statement_preference import (
    IasIncomeStatementPreference,
)
from seeker_accounting.modules.administration.models.permission import Permission
from seeker_accounting.modules.administration.models.auth_lockout import AuthenticationLockout
from seeker_accounting.modules.administration.models.password_history import PasswordHistory
from seeker_accounting.modules.administration.models.role import Role
from seeker_accounting.modules.administration.models.role_permission import RolePermission
from seeker_accounting.modules.administration.models.user import User
from seeker_accounting.modules.administration.models.user_company_access import UserCompanyAccess
from seeker_accounting.modules.administration.models.user_role import UserRole
from seeker_accounting.modules.administration.models.user_session import UserSession
from seeker_accounting.modules.companies.models.company import Company
from seeker_accounting.modules.companies.models.company_fiscal_default import CompanyFiscalDefault
from seeker_accounting.modules.companies.models.company_preference import CompanyPreference
from seeker_accounting.modules.companies.models.company_project_preference import CompanyProjectPreference
from seeker_accounting.modules.companies.models.system_admin_credential import SystemAdminCredential
from seeker_accounting.modules.contracts_projects.models.contract import Contract
from seeker_accounting.modules.contracts_projects.models.contract_change_order import ContractChangeOrder
from seeker_accounting.modules.contracts_projects.models.project import Project
from seeker_accounting.modules.contracts_projects.models.project_job import ProjectJob
from seeker_accounting.modules.contracts_projects.models.project_cost_code import ProjectCostCode
from seeker_accounting.modules.budgeting.models.project_budget_version import ProjectBudgetVersion
from seeker_accounting.modules.budgeting.models.project_budget_line import ProjectBudgetLine
from seeker_accounting.modules.job_costing.models.project_commitment import ProjectCommitment
from seeker_accounting.modules.job_costing.models.project_commitment_line import ProjectCommitmentLine
from seeker_accounting.modules.customers.models.customer import Customer
from seeker_accounting.modules.customers.models.customer_group import CustomerGroup
from seeker_accounting.modules.sales.models.sales_invoice import SalesInvoice
from seeker_accounting.modules.sales.models.sales_invoice_line import SalesInvoiceLine
from seeker_accounting.modules.sales.models.customer_quote import CustomerQuote
from seeker_accounting.modules.sales.models.customer_quote_line import CustomerQuoteLine
from seeker_accounting.modules.sales.models.sales_order import SalesOrder
from seeker_accounting.modules.sales.models.sales_order_line import SalesOrderLine
from seeker_accounting.modules.sales.models.sales_credit_note import SalesCreditNote
from seeker_accounting.modules.sales.models.sales_credit_note_line import SalesCreditNoteLine
from seeker_accounting.modules.sales.models.customer_receipt import CustomerReceipt
from seeker_accounting.modules.sales.models.customer_receipt_allocation import CustomerReceiptAllocation
from seeker_accounting.modules.suppliers.models.supplier import Supplier
from seeker_accounting.modules.suppliers.models.supplier_group import SupplierGroup
from seeker_accounting.modules.purchases.models.purchase_bill import PurchaseBill
from seeker_accounting.modules.purchases.models.purchase_bill_line import PurchaseBillLine
from seeker_accounting.modules.purchases.models.purchase_order import PurchaseOrder
from seeker_accounting.modules.purchases.models.purchase_order_line import PurchaseOrderLine
from seeker_accounting.modules.purchases.models.purchase_credit_note import PurchaseCreditNote
from seeker_accounting.modules.purchases.models.purchase_credit_note_line import PurchaseCreditNoteLine
from seeker_accounting.modules.purchases.models.supplier_payment import SupplierPayment
from seeker_accounting.modules.purchases.models.supplier_payment_allocation import SupplierPaymentAllocation
from seeker_accounting.modules.treasury.models.financial_account import FinancialAccount
from seeker_accounting.modules.treasury.models.treasury_transaction import TreasuryTransaction
from seeker_accounting.modules.treasury.models.treasury_transaction_line import TreasuryTransactionLine
from seeker_accounting.modules.treasury.models.treasury_transfer import TreasuryTransfer
from seeker_accounting.modules.treasury.models.bank_statement_import_batch import BankStatementImportBatch
from seeker_accounting.modules.treasury.models.bank_statement_line import BankStatementLine
from seeker_accounting.modules.treasury.models.bank_reconciliation_session import BankReconciliationSession
from seeker_accounting.modules.treasury.models.bank_reconciliation_match import BankReconciliationMatch
from seeker_accounting.modules.inventory.models.unit_of_measure import UnitOfMeasure
from seeker_accounting.modules.inventory.models.uom_category import UomCategory
from seeker_accounting.modules.inventory.models.item_category import ItemCategory
from seeker_accounting.modules.inventory.models.inventory_location import InventoryLocation
from seeker_accounting.modules.inventory.models.item import Item
from seeker_accounting.modules.inventory.models.inventory_document import InventoryDocument
from seeker_accounting.modules.inventory.models.inventory_document_line import InventoryDocumentLine
from seeker_accounting.modules.inventory.models.inventory_cost_layer import InventoryCostLayer
from seeker_accounting.modules.fixed_assets.models.asset_category import AssetCategory
from seeker_accounting.modules.fixed_assets.models.asset import Asset
from seeker_accounting.modules.fixed_assets.models.asset_depreciation_run import AssetDepreciationRun
from seeker_accounting.modules.fixed_assets.models.asset_depreciation_run_line import AssetDepreciationRunLine
from seeker_accounting.modules.fixed_assets.models.depreciation_method import DepreciationMethod
from seeker_accounting.modules.fixed_assets.models.macrs_profile import MacrsProfile
from seeker_accounting.modules.fixed_assets.models.asset_depreciation_settings import AssetDepreciationSettings
from seeker_accounting.modules.fixed_assets.models.asset_component import AssetComponent
from seeker_accounting.modules.fixed_assets.models.asset_usage_record import AssetUsageRecord
from seeker_accounting.modules.fixed_assets.models.asset_depreciation_pool import AssetDepreciationPool
from seeker_accounting.modules.fixed_assets.models.asset_depreciation_pool_member import AssetDepreciationPoolMember
from seeker_accounting.modules.fixed_assets.models.asset_depletion_profile import AssetDepletionProfile
from seeker_accounting.modules.payroll.models.company_payroll_setting import CompanyPayrollSetting
from seeker_accounting.modules.payroll.models.department import Department
from seeker_accounting.modules.payroll.models.position import Position
from seeker_accounting.modules.payroll.models.employee import Employee
from seeker_accounting.modules.payroll.models.payroll_component import PayrollComponent
from seeker_accounting.modules.payroll.models.payroll_rule_set import PayrollRuleSet
from seeker_accounting.modules.payroll.models.payroll_rule_bracket import PayrollRuleBracket
from seeker_accounting.modules.payroll.models.employee_compensation_profile import EmployeeCompensationProfile
from seeker_accounting.modules.payroll.models.employee_component_assignment import EmployeeComponentAssignment
from seeker_accounting.modules.payroll.models.payroll_input_batch import PayrollInputBatch
from seeker_accounting.modules.payroll.models.payroll_input_line import PayrollInputLine
from seeker_accounting.modules.payroll.models.payroll_run import PayrollRun
from seeker_accounting.modules.payroll.models.payroll_run_employee import PayrollRunEmployee
from seeker_accounting.modules.payroll.models.payroll_run_employee_project_allocation import (
    PayrollRunEmployeeProjectAllocation,
)
from seeker_accounting.modules.payroll.models.payroll_run_line import PayrollRunLine
from seeker_accounting.modules.payroll.models.payroll_payment_record import PayrollPaymentRecord
from seeker_accounting.modules.payroll.models.payroll_remittance_batch import PayrollRemittanceBatch
from seeker_accounting.modules.payroll.models.payroll_remittance_line import PayrollRemittanceLine
from seeker_accounting.modules.audit.models.audit_event import AuditEvent

MODEL_REGISTRY = (
    User,
    Role,
    Permission,
    AuthenticationLockout,
    PasswordHistory,
    RolePermission,
    UserRole,
    UserSession,
    Company,
    SystemAdminCredential,
    UserCompanyAccess,
    CompanyPreference,
    CompanyFiscalDefault,
    CompanyProjectPreference,
    Currency,
    Country,
    DocumentSequence,
    PaymentTerm,
    TaxCode,
    AccountClass,
    AccountType,
    Account,
    AccountRoleMapping,
    TaxCodeAccountMapping,
    IasIncomeStatementTemplate,
    IasIncomeStatementSection,
    IasIncomeStatementMapping,
    IasIncomeStatementPreference,
    FiscalYear,
    FiscalPeriod,
    JournalEntry,
    JournalEntryLine,
    CustomerGroup,
    Customer,
    SalesInvoice,
    SalesInvoiceLine,
    CustomerQuote,
    CustomerQuoteLine,
    SalesOrder,
    SalesOrderLine,
    SalesCreditNote,
    SalesCreditNoteLine,
    CustomerReceipt,
    CustomerReceiptAllocation,
    Contract,
    ContractChangeOrder,
    Project,
    ProjectJob,
    ProjectCostCode,
    ProjectBudgetVersion,
    ProjectBudgetLine,
    ProjectCommitment,
    ProjectCommitmentLine,
    SupplierGroup,
    Supplier,
    PurchaseBill,
    PurchaseBillLine,
    PurchaseCreditNote,
    PurchaseCreditNoteLine,
    SupplierPayment,
    SupplierPaymentAllocation,
    FinancialAccount,
    TreasuryTransaction,
    TreasuryTransactionLine,
    TreasuryTransfer,
    BankStatementImportBatch,
    BankStatementLine,
    BankReconciliationSession,
    BankReconciliationMatch,
    UnitOfMeasure,
    UomCategory,
    ItemCategory,
    InventoryLocation,
    Item,
    InventoryDocument,
    InventoryDocumentLine,
    InventoryCostLayer,
    AssetCategory,
    Asset,
    AssetDepreciationRun,
    AssetDepreciationRunLine,
    DepreciationMethod,
    MacrsProfile,
    AssetDepreciationSettings,
    AssetComponent,
    AssetUsageRecord,
    AssetDepreciationPool,
    AssetDepreciationPoolMember,
    AssetDepletionProfile,
    CompanyPayrollSetting,
    Department,
    Position,
    Employee,
    PayrollComponent,
    PayrollRuleSet,
    PayrollRuleBracket,
    EmployeeCompensationProfile,
    EmployeeComponentAssignment,
    PayrollInputBatch,
    PayrollInputLine,
    PayrollRun,
    PayrollRunEmployee,
    PayrollRunEmployeeProjectAllocation,
    PayrollRunLine,
    PayrollPaymentRecord,
    PayrollRemittanceBatch,
    PayrollRemittanceLine,
    AuditEvent,
)

target_metadata = Base.metadata


def load_model_registry() -> tuple[type[object], ...]:
    return MODEL_REGISTRY


__all__ = ["MODEL_REGISTRY", "load_model_registry", "target_metadata"]
