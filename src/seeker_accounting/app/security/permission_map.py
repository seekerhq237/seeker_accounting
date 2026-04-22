from __future__ import annotations

from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.payroll.payroll_permissions import (
    PAYROLL_AUDIT_VIEW,
    PAYROLL_COMPONENT_MANAGE,
    PAYROLL_EMPLOYEE_MANAGE,
    PAYROLL_INPUT_MANAGE,
    PAYROLL_PACK_APPLY,
    PAYROLL_PAYMENT_MANAGE,
    PAYROLL_PRINT,
    PAYROLL_REMITTANCE_MANAGE,
    PAYROLL_RULE_MANAGE,
    PAYROLL_RUN_APPROVE,
    PAYROLL_RUN_CALCULATE,
    PAYROLL_RUN_CREATE,
    PAYROLL_RUN_POST,
    PAYROLL_SETUP_MANAGE,
)

NAVIGATION_REQUIRED_PERMISSIONS: dict[str, tuple[str, ...]] = {
    nav_ids.COMPANIES: ("companies.view", "companies.select_active"),
    nav_ids.ORGANISATION_SETTINGS: ("companies.view",),
    nav_ids.CUSTOMERS: ("customers.view",),
    nav_ids.SUPPLIERS: ("suppliers.view",),
    nav_ids.PAYMENT_TERMS: ("reference.payment_terms.view",),
    nav_ids.TAX_CODES: ("reference.tax_codes.view",),
    nav_ids.DOCUMENT_SEQUENCES: ("reference.document_sequences.view",),
    nav_ids.ACCOUNT_ROLE_MAPPINGS: (
        "reference.account_role_mappings.view",
        "chart.role_mappings.view",
    ),
    nav_ids.CHART_OF_ACCOUNTS: ("chart.accounts.view",),
    nav_ids.FISCAL_PERIODS: ("fiscal.years.view", "fiscal.periods.view"),
    nav_ids.JOURNALS: ("journals.view",),
    nav_ids.SALES_INVOICES: ("sales.invoices.view",),
    nav_ids.CUSTOMER_QUOTES: ("sales.quotes.view",),
    nav_ids.SALES_ORDERS: ("sales.orders.view",),
    nav_ids.SALES_CREDIT_NOTES: ("sales.credit_notes.view",),
    nav_ids.CUSTOMER_RECEIPTS: ("sales.receipts.view",),
    nav_ids.PURCHASE_ORDERS: ("purchases.orders.view",),
    nav_ids.PURCHASE_CREDIT_NOTES: ("purchases.credit_notes.view",),
    nav_ids.PURCHASE_BILLS: ("purchases.bills.view",),
    nav_ids.SUPPLIER_PAYMENTS: ("purchases.payments.view",),
    nav_ids.FINANCIAL_ACCOUNTS: ("treasury.financial_accounts.view",),
    nav_ids.TREASURY_TRANSACTIONS: ("treasury.transactions.view",),
    nav_ids.TREASURY_TRANSFERS: ("treasury.transfers.view",),
    nav_ids.STATEMENT_LINES: ("treasury.statement_lines.view",),
    nav_ids.BANK_RECONCILIATION: ("treasury.reconciliation.view",),
    nav_ids.UNITS_OF_MEASURE: ("inventory.units.view",),
    nav_ids.ITEM_CATEGORIES: ("inventory.categories.view",),
    nav_ids.INVENTORY_LOCATIONS: ("inventory.locations.view",),
    nav_ids.ITEMS: ("inventory.items.view",),
    nav_ids.INVENTORY_DOCUMENTS: ("inventory.documents.view",),
    nav_ids.STOCK_POSITION: ("inventory.stock.view",),
    nav_ids.ASSET_CATEGORIES: ("assets.categories.view",),
    nav_ids.ASSETS: ("assets.master.view",),
    nav_ids.DEPRECIATION_RUNS: ("assets.runs.view",),
    nav_ids.CONTRACTS: ("contracts.view",),
    nav_ids.PROJECTS: ("projects.view",),
    nav_ids.PAYROLL_SETUP: (
        PAYROLL_SETUP_MANAGE,
        PAYROLL_EMPLOYEE_MANAGE,
        PAYROLL_COMPONENT_MANAGE,
        PAYROLL_RULE_MANAGE,
        PAYROLL_PACK_APPLY,
    ),
    nav_ids.PAYROLL_CALCULATION: (
        PAYROLL_RUN_CREATE,
        PAYROLL_RUN_CALCULATE,
        PAYROLL_RUN_APPROVE,
    ),
    nav_ids.PAYROLL_ACCOUNTING: (
        PAYROLL_RUN_POST,
        PAYROLL_PAYMENT_MANAGE,
        PAYROLL_REMITTANCE_MANAGE,
    ),
    nav_ids.PAYROLL_OPERATIONS: (
        PAYROLL_INPUT_MANAGE,
        PAYROLL_PRINT,
        PAYROLL_AUDIT_VIEW,
    ),
    nav_ids.REPORTS: (
        "reports.trial_balance.view",
        "reports.general_ledger.view",
        "reports.ohada_income_statement.view",
        "reports.ias_income_statement.view",
        "reports.ohada_balance_sheet.view",
        "reports.ias_balance_sheet.view",
        "reports.ar_aging.view",
        "reports.ap_aging.view",
        "reports.customer_statements.view",
        "reports.supplier_statements.view",
        "reports.payroll_summary.view",
        "reports.treasury_reports.view",
        "reports.financial_analysis.view",
    ),
    nav_ids.PROJECT_VARIANCE_ANALYSIS: ("management.project_variance.view",),
    nav_ids.CONTRACT_SUMMARY: ("management.contract_summary.view",),
    nav_ids.ADMINISTRATION: ("administration.users.view",),
    nav_ids.ROLES: ("administration.roles.view",),
    nav_ids.AUDIT_LOG: ("audit.view",),
    nav_ids.BACKUP_RESTORE: ("administration.backup.export", "administration.backup.import"),
}


def required_permissions_for_nav(nav_id: str) -> tuple[str, ...]:
    return NAVIGATION_REQUIRED_PERMISSIONS.get(nav_id, ())


def primary_permission_for_nav(nav_id: str) -> str | None:
    required_permissions = required_permissions_for_nav(nav_id)
    return required_permissions[0] if required_permissions else None


def can_access_navigation(permission_service: PermissionService, nav_id: str) -> bool:
    required_permissions = required_permissions_for_nav(nav_id)
    if not required_permissions:
        return True
    return permission_service.has_any_permission(required_permissions)


def build_navigation_denied_message(permission_service: PermissionService, nav_id: str) -> str:
    primary_permission = primary_permission_for_nav(nav_id)
    if primary_permission is None:
        return "You do not have permission to open this page."
    return permission_service.build_denied_message(primary_permission)


# ---------------------------------------------------------------------------
# Reporting-level permission maps
# Keys match tab_key / tile_key in ReportingWorkspaceService.
# ---------------------------------------------------------------------------

REPORT_TAB_PERMISSIONS: dict[str, str] = {
    "trial_balance": "reports.trial_balance.view",
    "general_ledger": "reports.general_ledger.view",
}

REPORT_TILE_PERMISSIONS: dict[str, str] = {
    "ohada_income_statement": "reports.ohada_income_statement.view",
    "ias_income_statement": "reports.ias_income_statement.view",
    "ohada_balance_sheet": "reports.ohada_balance_sheet.view",
    "ias_balance_sheet": "reports.ias_balance_sheet.view",
    "ar_aging": "reports.ar_aging.view",
    "ap_aging": "reports.ap_aging.view",
    "customer_statements": "reports.customer_statements.view",
    "supplier_statements": "reports.supplier_statements.view",
    "payroll_summary": "reports.payroll_summary.view",
    "treasury_reports": "reports.treasury_reports.view",
    "financial_analysis": "reports.financial_analysis.view",
}

REPORT_PRINT_PERMISSIONS: dict[str, str] = {
    "trial_balance": "reports.trial_balance.print",
    "general_ledger": "reports.general_ledger.print",
    "ohada_income_statement": "reports.ohada_income_statement.print",
    "ias_income_statement": "reports.ias_income_statement.print",
    "ohada_balance_sheet": "reports.ohada_balance_sheet.print",
    "ias_balance_sheet": "reports.ias_balance_sheet.print",
    "ar_aging": "reports.ar_aging.print",
    "ap_aging": "reports.ap_aging.print",
    "customer_statements": "reports.customer_statements.print",
    "supplier_statements": "reports.supplier_statements.print",
    "payroll_summary": "reports.payroll_summary.print",
    "treasury_reports": "reports.treasury_reports.print",
    "financial_analysis": "reports.financial_analysis.print",
}
