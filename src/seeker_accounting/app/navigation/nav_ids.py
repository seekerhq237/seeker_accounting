from __future__ import annotations

from typing import Final

DASHBOARD: Final = "dashboard"
COMPANIES: Final = "companies"
CUSTOMERS: Final = "customers"
SUPPLIERS: Final = "suppliers"
PAYMENT_TERMS: Final = "payment_terms"
TAX_CODES: Final = "tax_codes"
DOCUMENT_SEQUENCES: Final = "document_sequences"
CHART_OF_ACCOUNTS: Final = "chart_of_accounts"
ACCOUNT_ROLE_MAPPINGS: Final = "account_role_mappings"
FISCAL_PERIODS: Final = "fiscal_periods"
JOURNALS: Final = "journals"
CUSTOMER_QUOTES: Final = "customer_quotes"
SALES_ORDERS: Final = "sales_orders"
SALES_CREDIT_NOTES: Final = "sales_credit_notes"
SALES_INVOICES: Final = "sales_invoices"
CUSTOMER_RECEIPTS: Final = "customer_receipts"
PURCHASE_ORDERS: Final = "purchase_orders"
PURCHASE_CREDIT_NOTES: Final = "purchase_credit_notes"
PURCHASE_BILLS: Final = "purchase_bills"
SUPPLIER_PAYMENTS: Final = "supplier_payments"
FINANCIAL_ACCOUNTS: Final = "financial_accounts"
TREASURY_TRANSACTIONS: Final = "treasury_transactions"
TREASURY_TRANSFERS: Final = "treasury_transfers"
STATEMENT_LINES: Final = "statement_lines"
BANK_RECONCILIATION: Final = "bank_reconciliation"
UOM_CATEGORIES: Final = "uom_categories"
UNITS_OF_MEASURE: Final = "units_of_measure"
ITEM_CATEGORIES: Final = "item_categories"
INVENTORY_LOCATIONS: Final = "inventory_locations"
ITEMS: Final = "items"
INVENTORY_DOCUMENTS: Final = "inventory_documents"
STOCK_POSITION: Final = "stock_position"
ASSET_CATEGORIES: Final = "asset_categories"
ASSETS: Final = "assets"
DEPRECIATION_RUNS: Final = "depreciation_runs"
CONTRACTS: Final = "contracts"
PROJECTS: Final = "projects"
PAYROLL_SETUP: Final = "payroll_setup"
PAYROLL_CALCULATION: Final = "payroll_calculation"
PAYROLL_ACCOUNTING: Final = "payroll_accounting"
PAYROLL_OPERATIONS: Final = "payroll_operations"
REPORTS: Final = "reports"
PROJECT_VARIANCE_ANALYSIS: Final = "project_variance_analysis"
CONTRACT_SUMMARY: Final = "contract_summary"
ADMINISTRATION: Final = "administration"
ROLES: Final = "roles"
AUDIT_LOG: Final = "audit_log"
ORGANISATION_SETTINGS: Final = "organisation_settings"
BACKUP_RESTORE: Final = "backup_restore"

# ── Entity detail workspaces (Phase 3) ─────────────────────────────────
CUSTOMER_DETAIL: Final = "customer_detail"
SUPPLIER_DETAIL: Final = "supplier_detail"
ACCOUNT_DETAIL: Final = "account_detail"
ITEM_DETAIL: Final = "item_detail"
# ── Document detail workspaces (Phase 5) ───────────────────────────────────────
SALES_INVOICE_DETAIL: Final = "sales_invoice_detail"
PURCHASE_BILL_DETAIL: Final = "purchase_bill_detail"
ALL_NAV_IDS: Final[tuple[str, ...]] = (
    DASHBOARD,
    COMPANIES,
    CUSTOMERS,
    SUPPLIERS,
    PAYMENT_TERMS,
    TAX_CODES,
    DOCUMENT_SEQUENCES,
    CHART_OF_ACCOUNTS,
    ACCOUNT_ROLE_MAPPINGS,
    FISCAL_PERIODS,
    JOURNALS,
    CUSTOMER_QUOTES,
    SALES_ORDERS,
    SALES_CREDIT_NOTES,
    SALES_INVOICES,
    CUSTOMER_RECEIPTS,
    PURCHASE_ORDERS,
    PURCHASE_CREDIT_NOTES,
    PURCHASE_BILLS,
    SUPPLIER_PAYMENTS,
    FINANCIAL_ACCOUNTS,
    TREASURY_TRANSACTIONS,
    TREASURY_TRANSFERS,
    STATEMENT_LINES,
    BANK_RECONCILIATION,
    UOM_CATEGORIES,
    UNITS_OF_MEASURE,
    ITEM_CATEGORIES,
    INVENTORY_LOCATIONS,
    ITEMS,
    INVENTORY_DOCUMENTS,
    STOCK_POSITION,
    ASSET_CATEGORIES,
    ASSETS,
    DEPRECIATION_RUNS,
    CONTRACTS,
    PROJECTS,
    PAYROLL_SETUP,
    PAYROLL_CALCULATION,
    PAYROLL_ACCOUNTING,
    PAYROLL_OPERATIONS,
    REPORTS,
    PROJECT_VARIANCE_ANALYSIS,
    CONTRACT_SUMMARY,
    ADMINISTRATION,
    ROLES,
    AUDIT_LOG,
    ORGANISATION_SETTINGS,
    BACKUP_RESTORE,
    # Phase 3 entity detail workspaces
    CUSTOMER_DETAIL,
    SUPPLIER_DETAIL,
    ACCOUNT_DETAIL,
    ITEM_DETAIL,
    # Phase 5 document detail workspaces
    SALES_INVOICE_DETAIL,
    PURCHASE_BILL_DETAIL,
)

DEFAULT_NAV_ID: Final = DASHBOARD
