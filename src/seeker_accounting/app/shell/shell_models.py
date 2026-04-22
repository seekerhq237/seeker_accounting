from __future__ import annotations

from dataclasses import dataclass

from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.shared.enums.module_codes import ModuleCode
from seeker_accounting.shared.enums.status_codes import StatusCode


@dataclass(frozen=True, slots=True)
class NavigationItem:
    nav_id: str
    label: str
    section_label: str
    description: str
    module_code: ModuleCode


@dataclass(frozen=True, slots=True)
class NavigationSection:
    title: str
    items: tuple[NavigationItem, ...]


@dataclass(frozen=True, slots=True)
class PlaceholderPageModel:
    nav_id: str
    title: str
    summary: str
    status_code: StatusCode
    available_now: tuple[str, ...]
    next_slice: tuple[str, ...]


# ── Sidebar accordion model ──────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SidebarChild:
    nav_id: str
    label: str


@dataclass(frozen=True, slots=True)
class SidebarModule:
    key: str
    label: str
    children: tuple[SidebarChild, ...]


SIDEBAR_MODULES: tuple[SidebarModule, ...] = (
    SidebarModule(
        key="dashboard",
        label="Home",
        children=(
            SidebarChild(nav_id=nav_ids.DASHBOARD, label="Home"),
        ),
    ),
    SidebarModule(
        key="third_parties",
        label="Third Parties",
        children=(
            SidebarChild(nav_id=nav_ids.CUSTOMERS, label="Customers"),
            SidebarChild(nav_id=nav_ids.SUPPLIERS, label="Suppliers"),
        ),
    ),
    SidebarModule(
        key="accounting",
        label="Accounting",
        children=(
            SidebarChild(nav_id=nav_ids.PAYMENT_TERMS, label="Payment Terms"),
            SidebarChild(nav_id=nav_ids.TAX_CODES, label="Tax Codes"),
            SidebarChild(nav_id=nav_ids.DOCUMENT_SEQUENCES, label="Document Sequences"),
            SidebarChild(nav_id=nav_ids.ACCOUNT_ROLE_MAPPINGS, label="Account Role Mappings"),
            SidebarChild(nav_id=nav_ids.CHART_OF_ACCOUNTS, label="Chart of Accounts"),
            SidebarChild(nav_id=nav_ids.FISCAL_PERIODS, label="Fiscal Periods"),
            SidebarChild(nav_id=nav_ids.JOURNALS, label="Journal"),
        ),
    ),
    SidebarModule(
        key="sales",
        label="Sales",
        children=(
            SidebarChild(nav_id=nav_ids.CUSTOMER_QUOTES, label="Customer Quotes"),
            SidebarChild(nav_id=nav_ids.SALES_ORDERS, label="Sales Orders"),
            SidebarChild(nav_id=nav_ids.SALES_CREDIT_NOTES, label="Credit Notes"),
            SidebarChild(nav_id=nav_ids.SALES_INVOICES, label="Sales Invoices"),
            SidebarChild(nav_id=nav_ids.CUSTOMER_RECEIPTS, label="Customer Receipts"),
        ),
    ),
    SidebarModule(
        key="purchases",
        label="Purchases",
        children=(
            SidebarChild(nav_id=nav_ids.PURCHASE_ORDERS, label="Purchase Orders"),
            SidebarChild(nav_id=nav_ids.PURCHASE_CREDIT_NOTES, label="Credit Notes"),
            SidebarChild(nav_id=nav_ids.PURCHASE_BILLS, label="Purchase Bills"),
            SidebarChild(nav_id=nav_ids.SUPPLIER_PAYMENTS, label="Supplier Payments"),
        ),
    ),
    SidebarModule(
        key="treasury",
        label="Treasury",
        children=(
            SidebarChild(nav_id=nav_ids.FINANCIAL_ACCOUNTS, label="Financial Accounts"),
            SidebarChild(nav_id=nav_ids.TREASURY_TRANSACTIONS, label="Transactions"),
            SidebarChild(nav_id=nav_ids.TREASURY_TRANSFERS, label="Transfers"),
            SidebarChild(nav_id=nav_ids.STATEMENT_LINES, label="Bank Statements"),
            SidebarChild(nav_id=nav_ids.BANK_RECONCILIATION, label="Reconciliation"),
        ),
    ),
    SidebarModule(
        key="inventory",
        label="Inventory",
        children=(
            SidebarChild(nav_id=nav_ids.UOM_CATEGORIES, label="UoM Categories"),
            SidebarChild(nav_id=nav_ids.UNITS_OF_MEASURE, label="Units of Measure"),
            SidebarChild(nav_id=nav_ids.ITEM_CATEGORIES, label="Item Categories"),
            SidebarChild(nav_id=nav_ids.INVENTORY_LOCATIONS, label="Inventory Locations"),
            SidebarChild(nav_id=nav_ids.ITEMS, label="Items"),
            SidebarChild(nav_id=nav_ids.INVENTORY_DOCUMENTS, label="Inventory Documents"),
            SidebarChild(nav_id=nav_ids.STOCK_POSITION, label="Stock Position"),
        ),
    ),
    SidebarModule(
        key="fixed_assets",
        label="Fixed Assets",
        children=(
            SidebarChild(nav_id=nav_ids.ASSET_CATEGORIES, label="Asset Categories"),
            SidebarChild(nav_id=nav_ids.ASSETS, label="Asset Register"),
            SidebarChild(nav_id=nav_ids.DEPRECIATION_RUNS, label="Depreciation Runs"),
        ),
    ),
    SidebarModule(
        key="projects",
        label="Projects",
        children=(
            SidebarChild(nav_id=nav_ids.CONTRACTS, label="Contracts"),
            SidebarChild(nav_id=nav_ids.PROJECTS, label="Projects"),
        ),
    ),
    SidebarModule(
        key="payroll",
        label="Payroll",
        children=(
            SidebarChild(nav_id=nav_ids.PAYROLL_SETUP, label="Payroll Setup"),
            SidebarChild(nav_id=nav_ids.PAYROLL_CALCULATION, label="Payroll Runs"),
            SidebarChild(nav_id=nav_ids.PAYROLL_ACCOUNTING, label="Payroll Accounting"),
            SidebarChild(nav_id=nav_ids.PAYROLL_OPERATIONS, label="Payroll Operations"),
        ),
    ),
    SidebarModule(
        key="reports",
        label="Reports",
        children=(
            SidebarChild(nav_id=nav_ids.REPORTS, label="Reports"),
            SidebarChild(nav_id=nav_ids.PROJECT_VARIANCE_ANALYSIS, label="Project Variance"),
            SidebarChild(nav_id=nav_ids.CONTRACT_SUMMARY, label="Contract Summary"),
        ),
    ),
    SidebarModule(
        key="administration",
        label="Administration",
        children=(
            SidebarChild(nav_id=nav_ids.ORGANISATION_SETTINGS, label="Organisation Settings"),
            SidebarChild(nav_id=nav_ids.ADMINISTRATION, label="Users"),
            SidebarChild(nav_id=nav_ids.ROLES, label="Roles"),
            SidebarChild(nav_id=nav_ids.AUDIT_LOG, label="Audit Log"),
            SidebarChild(nav_id=nav_ids.BACKUP_RESTORE, label="Backup & Restore"),
        ),
    ),
)

NAV_ID_TO_MODULE_KEY: dict[str, str] = {
    child.nav_id: module.key
    for module in SIDEBAR_MODULES
    for child in module.children
}


NAVIGATION_SECTIONS: tuple[NavigationSection, ...] = (
    NavigationSection(
        title="Overview",
        items=(
            NavigationItem(
                nav_id=nav_ids.DASHBOARD,
                label="Home",
                section_label="Overview",
                description="Overview",
                module_code=ModuleCode.DASHBOARD,
            ),
        ),
    ),
    NavigationSection(
        title="Parties",
        items=(
            NavigationItem(
                nav_id=nav_ids.CUSTOMERS,
                label="Customers",
                section_label="Parties",
                description="Customer masters",
                module_code=ModuleCode.CUSTOMERS,
            ),
            NavigationItem(
                nav_id=nav_ids.SUPPLIERS,
                label="Suppliers",
                section_label="Parties",
                description="Supplier masters",
                module_code=ModuleCode.SUPPLIERS,
            ),
        ),
    ),
    NavigationSection(
        title="Accounting Setup",
        items=(
            NavigationItem(
                nav_id=nav_ids.PAYMENT_TERMS,
                label="Payment Terms",
                section_label="Accounting Setup",
                description="Customer and supplier due terms",
                module_code=ModuleCode.PAYMENT_TERMS,
            ),
            NavigationItem(
                nav_id=nav_ids.TAX_CODES,
                label="Tax Codes",
                section_label="Accounting Setup",
                description="Company tax definitions",
                module_code=ModuleCode.TAX_CODES,
            ),
            NavigationItem(
                nav_id=nav_ids.DOCUMENT_SEQUENCES,
                label="Document Sequences",
                section_label="Accounting Setup",
                description="Company numbering definitions",
                module_code=ModuleCode.DOCUMENT_SEQUENCES,
            ),
            NavigationItem(
                nav_id=nav_ids.ACCOUNT_ROLE_MAPPINGS,
                label="Account Role Mappings",
                section_label="Accounting Setup",
                description="Control account role assignments",
                module_code=ModuleCode.ACCOUNT_ROLE_MAPPINGS,
            ),
        ),
    ),
    NavigationSection(
        title="Accounting",
        items=(
            NavigationItem(
                nav_id=nav_ids.CHART_OF_ACCOUNTS,
                label="Chart of Accounts",
                section_label="Accounting",
                description="Account structure",
                module_code=ModuleCode.CHART_OF_ACCOUNTS,
            ),
            NavigationItem(
                nav_id=nav_ids.FISCAL_PERIODS,
                label="Fiscal Periods",
                section_label="Accounting",
                description="Periods and close",
                module_code=ModuleCode.FISCAL_PERIODS,
            ),
            NavigationItem(
                nav_id=nav_ids.JOURNALS,
                label="Journals",
                section_label="Accounting",
                description="Journal entry",
                module_code=ModuleCode.JOURNALS,
            ),
        ),
    ),
    NavigationSection(
        title="Sales",
        items=(
            NavigationItem(
                nav_id=nav_ids.CUSTOMER_QUOTES,
                label="Customer Quotes",
                section_label="Sales",
                description="Customer quote and estimate documents",
                module_code=ModuleCode.CUSTOMER_QUOTES,
            ),
            NavigationItem(
                nav_id=nav_ids.SALES_ORDERS,
                label="Sales Orders",
                section_label="Sales",
                description="Sales order documents",
                module_code=ModuleCode.SALES_ORDERS,
            ),
            NavigationItem(
                nav_id=nav_ids.SALES_CREDIT_NOTES,
                label="Sales Credit Notes",
                section_label="Sales",
                description="Sales credit note documents",
                module_code=ModuleCode.SALES_CREDIT_NOTES,
            ),
            NavigationItem(
                nav_id=nav_ids.SALES_INVOICES,
                label="Sales Invoices",
                section_label="Sales",
                description="Sales invoice documents",
                module_code=ModuleCode.SALES_INVOICES,
            ),
            NavigationItem(
                nav_id=nav_ids.CUSTOMER_RECEIPTS,
                label="Customer Receipts",
                section_label="Sales",
                description="Customer receipt documents",
                module_code=ModuleCode.CUSTOMER_RECEIPTS,
            ),
        ),
    ),
    NavigationSection(
        title="Purchases",
        items=(
            NavigationItem(
                nav_id=nav_ids.PURCHASE_ORDERS,
                label="Purchase Orders",
                section_label="Purchases",
                description="Purchase order and procurement documents",
                module_code=ModuleCode.PURCHASE_ORDERS,
            ),
            NavigationItem(
                nav_id=nav_ids.PURCHASE_CREDIT_NOTES,
                label="Purchase Credit Notes",
                section_label="Purchases",
                description="Purchase credit note documents",
                module_code=ModuleCode.PURCHASE_CREDIT_NOTES,
            ),
            NavigationItem(
                nav_id=nav_ids.PURCHASE_BILLS,
                label="Purchase Bills",
                section_label="Purchases",
                description="Purchase bill documents",
                module_code=ModuleCode.PURCHASE_BILLS,
            ),
            NavigationItem(
                nav_id=nav_ids.SUPPLIER_PAYMENTS,
                label="Supplier Payments",
                section_label="Purchases",
                description="Supplier payment documents",
                module_code=ModuleCode.SUPPLIER_PAYMENTS,
            ),
        ),
    ),
    NavigationSection(
        title="Treasury",
        items=(
            NavigationItem(
                nav_id=nav_ids.FINANCIAL_ACCOUNTS,
                label="Financial Accounts",
                section_label="Treasury",
                description="Bank and cash accounts",
                module_code=ModuleCode.FINANCIAL_ACCOUNTS,
            ),
            NavigationItem(
                nav_id=nav_ids.TREASURY_TRANSACTIONS,
                label="Transactions",
                section_label="Treasury",
                description="Cash and bank transactions",
                module_code=ModuleCode.TREASURY_TRANSACTIONS,
            ),
            NavigationItem(
                nav_id=nav_ids.TREASURY_TRANSFERS,
                label="Transfers",
                section_label="Treasury",
                description="Inter-account transfers",
                module_code=ModuleCode.TREASURY_TRANSFERS,
            ),
            NavigationItem(
                nav_id=nav_ids.STATEMENT_LINES,
                label="Bank Statements",
                section_label="Treasury",
                description="Imported statement lines",
                module_code=ModuleCode.STATEMENT_LINES,
            ),
            NavigationItem(
                nav_id=nav_ids.BANK_RECONCILIATION,
                label="Reconciliation",
                section_label="Treasury",
                description="Bank reconciliation sessions",
                module_code=ModuleCode.BANK_RECONCILIATION,
            ),
        ),
    ),
    NavigationSection(
        title="Inventory",
        items=(
            NavigationItem(
                nav_id=nav_ids.UOM_CATEGORIES,
                label="UoM Categories",
                section_label="Inventory",
                description="Group related units for conversion",
                module_code=ModuleCode.UOM_CATEGORIES,
            ),
            NavigationItem(
                nav_id=nav_ids.UNITS_OF_MEASURE,
                label="Units of Measure",
                section_label="Inventory",
                description="UoM reference data",
                module_code=ModuleCode.UNITS_OF_MEASURE,
            ),
            NavigationItem(
                nav_id=nav_ids.ITEM_CATEGORIES,
                label="Item Categories",
                section_label="Inventory",
                description="Item category groupings",
                module_code=ModuleCode.ITEM_CATEGORIES,
            ),
            NavigationItem(
                nav_id=nav_ids.INVENTORY_LOCATIONS,
                label="Inventory Locations",
                section_label="Inventory",
                description="Warehouse and bin locations",
                module_code=ModuleCode.INVENTORY_LOCATIONS,
            ),
            NavigationItem(
                nav_id=nav_ids.ITEMS,
                label="Items",
                section_label="Inventory",
                description="Item master data",
                module_code=ModuleCode.ITEMS,
            ),
            NavigationItem(
                nav_id=nav_ids.INVENTORY_DOCUMENTS,
                label="Inventory Documents",
                section_label="Inventory",
                description="Receipts, issues, and adjustments",
                module_code=ModuleCode.INVENTORY_DOCUMENTS,
            ),
            NavigationItem(
                nav_id=nav_ids.STOCK_POSITION,
                label="Stock Position",
                section_label="Inventory",
                description="Stock on hand and valuation",
                module_code=ModuleCode.STOCK_POSITION,
            ),
        ),
    ),
    NavigationSection(
        title="Fixed Assets",
        items=(
            NavigationItem(
                nav_id=nav_ids.ASSET_CATEGORIES,
                label="Asset Categories",
                section_label="Fixed Assets",
                description="Category account mapping and defaults",
                module_code=ModuleCode.ASSET_CATEGORIES,
            ),
            NavigationItem(
                nav_id=nav_ids.ASSETS,
                label="Asset Register",
                section_label="Fixed Assets",
                description="Fixed asset register",
                module_code=ModuleCode.ASSETS,
            ),
            NavigationItem(
                nav_id=nav_ids.DEPRECIATION_RUNS,
                label="Depreciation Runs",
                section_label="Fixed Assets",
                description="Monthly depreciation run and posting",
                module_code=ModuleCode.DEPRECIATION_RUNS,
            ),
        ),
    ),
    NavigationSection(
        title="Projects",
        items=(
            NavigationItem(
                nav_id=nav_ids.CONTRACTS,
                label="Contracts",
                section_label="Projects",
                description="Contract master records",
                module_code=ModuleCode.CONTRACTS,
            ),
            NavigationItem(
                nav_id=nav_ids.PROJECTS,
                label="Projects",
                section_label="Projects",
                description="Project master records",
                module_code=ModuleCode.PROJECTS,
            ),
        ),
    ),
    NavigationSection(
        title="Payroll",
        items=(
            NavigationItem(
                nav_id=nav_ids.PAYROLL_SETUP,
                label="Payroll Setup",
                section_label="Payroll",
                description="Payroll configuration, employees, components, and rules",
                module_code=ModuleCode.PAYROLL_SETUP,
            ),
            NavigationItem(
                nav_id=nav_ids.PAYROLL_CALCULATION,
                label="Payroll Runs",
                section_label="Payroll",
                description="Compensation profiles, component assignments, variable inputs, and payroll run calculation",
                module_code=ModuleCode.PAYROLL_CALCULATION,
            ),
            NavigationItem(
                nav_id=nav_ids.PAYROLL_ACCOUNTING,
                label="Payroll Accounting",
                section_label="Payroll",
                description="Post payroll runs to the GL, track employee payment settlements, manage statutory remittances",
                module_code=ModuleCode.PAYROLL_ACCOUNTING,
            ),
            NavigationItem(
                nav_id=nav_ids.PAYROLL_OPERATIONS,
                label="Payroll Operations",
                section_label="Payroll",
                description="Validation dashboard, statutory packs, imports, print payslips, audit log",
                module_code=ModuleCode.PAYROLL_OPERATIONS,
            ),
        ),
    ),
    NavigationSection(
        title="Reports",
        items=(
            NavigationItem(
                nav_id=nav_ids.REPORTS,
                label="Reports",
                section_label="Reports",
                description="Reporting",
                module_code=ModuleCode.REPORTS,
            ),
            NavigationItem(
                nav_id=nav_ids.PROJECT_VARIANCE_ANALYSIS,
                label="Project Variance",
                section_label="Reports",
                description="Budget control, variance breakdown, and cost trend analysis by project",
                module_code=ModuleCode.PROJECT_VARIANCE_ANALYSIS,
            ),
            NavigationItem(
                nav_id=nav_ids.CONTRACT_SUMMARY,
                label="Contract Summary",
                section_label="Reports",
                description="Financial summary and project rollup by contract",
                module_code=ModuleCode.CONTRACT_SUMMARY,
            ),
        ),
    ),
    NavigationSection(
        title="Administration",
        items=(
            NavigationItem(
                nav_id=nav_ids.ORGANISATION_SETTINGS,
                label="Organisation Settings",
                section_label="Administration",
                description="Company profile and operating context",
                module_code=ModuleCode.ORGANISATION_SETTINGS,
            ),
            NavigationItem(
                nav_id=nav_ids.ADMINISTRATION,
                label="Users",
                section_label="Administration",
                description="Users and access",
                module_code=ModuleCode.ADMINISTRATION,
            ),
            NavigationItem(
                nav_id=nav_ids.ROLES,
                label="Roles",
                section_label="Administration",
                description="Roles and permission assignment",
                module_code=ModuleCode.ADMINISTRATION,
            ),
        ),
    ),
)

NAVIGATION_BY_ID = {
    item.nav_id: item
    for section in NAVIGATION_SECTIONS
    for item in section.items
}

# Backward compatibility: COMPANIES was removed from visible navigation
# but may still be referenced by workspace pages or programmatic navigation.
NAVIGATION_BY_ID.setdefault(
    nav_ids.COMPANIES,
    NavigationItem(
        nav_id=nav_ids.COMPANIES,
        label="Companies",
        section_label="Administration",
        description="Company context",
        module_code=ModuleCode.COMPANIES,
    ),
)

PLACEHOLDER_PAGES = {
    nav_ids.DASHBOARD: PlaceholderPageModel(
        nav_id=nav_ids.DASHBOARD,
        title="Dashboard",
        summary="A calm overview space for business signals, close status, and daily accounting priorities.",
        status_code=StatusCode.READY,
        available_now=(
            "KPI and alert surfaces",
            "Operational drilldowns",
        ),
        next_slice=(
            "Period-over-period comparisons",
            "Dashboard preferences",
        ),
    ),
    nav_ids.COMPANIES: PlaceholderPageModel(
        nav_id=nav_ids.COMPANIES,
        title="Companies",
        summary="Organisation management has moved to Administration > Organisation Settings.",
        status_code=StatusCode.PLACEHOLDER,
        available_now=(),
        next_slice=(),
    ),
    nav_ids.ORGANISATION_SETTINGS: PlaceholderPageModel(
        nav_id=nav_ids.ORGANISATION_SETTINGS,
        title="Organisation Settings",
        summary="Manage company master data and operating context from a structured administration workspace.",
        status_code=StatusCode.READY,
        available_now=(
            "View and edit company profiles",
            "Switch active company context",
            "Company directory overview",
        ),
        next_slice=(
            "Company preferences management",
            "Fiscal defaults configuration",
        ),
    ),
    nav_ids.CUSTOMERS: PlaceholderPageModel(
        nav_id=nav_ids.CUSTOMERS,
        title="Customers",
        summary="Customer master data belongs in a compact, company-scoped workspace with clean readiness signals for later receivables flows.",
        status_code=StatusCode.PLACEHOLDER,
        available_now=(
            "Company-scoped list workspace",
            "Create and edit dialogs",
        ),
        next_slice=(
            "Receivables source workflows",
            "Aging and statement outputs",
        ),
    ),
    nav_ids.SUPPLIERS: PlaceholderPageModel(
        nav_id=nav_ids.SUPPLIERS,
        title="Suppliers",
        summary="Supplier master data belongs in a compact, company-scoped workspace with clean readiness signals for later payables flows.",
        status_code=StatusCode.PLACEHOLDER,
        available_now=(
            "Company-scoped list workspace",
            "Create and edit dialogs",
        ),
        next_slice=(
            "Payables source workflows",
            "Aging and statement outputs",
        ),
    ),
    nav_ids.PAYMENT_TERMS: PlaceholderPageModel(
        nav_id=nav_ids.PAYMENT_TERMS,
        title="Payment Terms",
        summary="Payment terms should stay compact, company-scoped, and easy to maintain from a focused setup workspace.",
        status_code=StatusCode.PLACEHOLDER,
        available_now=(
            "Company-scoped table workspace",
            "Create and edit dialogs",
        ),
        next_slice=(
            "Document workflow adoption",
            "Reference usage analytics",
        ),
    ),
    nav_ids.TAX_CODES: PlaceholderPageModel(
        nav_id=nav_ids.TAX_CODES,
        title="Tax Codes",
        summary="Tax setup should remain explicit, effective-dated, and visible in a dense but calm maintenance surface.",
        status_code=StatusCode.PLACEHOLDER,
        available_now=(
            "Company-scoped table workspace",
            "Create and edit dialogs",
        ),
        next_slice=(
            "Account mappings after chart slice",
            "Broader tax workflow integration",
        ),
    ),
    nav_ids.DOCUMENT_SEQUENCES: PlaceholderPageModel(
        nav_id=nav_ids.DOCUMENT_SEQUENCES,
        title="Document Sequences",
        summary="Numbering definitions belong in a disciplined company-scoped workspace with preview-only flows in the first pass.",
        status_code=StatusCode.PLACEHOLDER,
        available_now=(
            "Company-scoped table workspace",
            "Preview-only numbering flow",
        ),
        next_slice=(
            "Sequence issuance workflow",
            "Operational document integration",
        ),
    ),
    nav_ids.CHART_OF_ACCOUNTS: PlaceholderPageModel(
        nav_id=nav_ids.CHART_OF_ACCOUNTS,
        title="Chart of Accounts",
        summary="This workspace is reserved for the account structure, hierarchy, and maintenance controls.",
        status_code=StatusCode.PLACEHOLDER,
        available_now=(
            "Locked route for the module",
            "Table and form styling foundation",
        ),
        next_slice=(
            "Account tree and details",
            "Create and edit actions",
        ),
    ),
    nav_ids.ACCOUNT_ROLE_MAPPINGS: PlaceholderPageModel(
        nav_id=nav_ids.ACCOUNT_ROLE_MAPPINGS,
        title="Account Role Mappings",
        summary="Assign controlled accounting roles to chart accounts so posting workflows resolve control accounts automatically.",
        status_code=StatusCode.PLACEHOLDER,
        available_now=(
            "Standalone role mapping workspace",
            "Guided blocker destination for AR/AP control",
        ),
        next_slice=(
            "Broader role coverage",
            "Guided flow from additional modules",
        ),
    ),
    nav_ids.FISCAL_PERIODS: PlaceholderPageModel(
        nav_id=nav_ids.FISCAL_PERIODS,
        title="Fiscal Periods",
        summary="Fiscal setup will live here, including periods, close status, and control dates.",
        status_code=StatusCode.PLACEHOLDER,
        available_now=(
            "Dedicated fiscal route",
            "Visible fiscal placeholder in chrome",
        ),
        next_slice=(
            "Period list and close controls",
            "Validation tied to fiscal state",
        ),
    ),
    nav_ids.JOURNALS: PlaceholderPageModel(
        nav_id=nav_ids.JOURNALS,
        title="Journals",
        summary="Journal entry and posting workflows will be hosted here in a dense accounting surface.",
        status_code=StatusCode.PLACEHOLDER,
        available_now=(
            "Reserved journal workspace",
            "Shell support for module switching",
        ),
        next_slice=(
            "Entry grid and balancing",
            "Posting orchestration",
        ),
    ),
    nav_ids.SALES_INVOICES: PlaceholderPageModel(
        nav_id=nav_ids.SALES_INVOICES,
        title="Sales Invoices",
        summary="Create, review, and post sales invoices as controlled source documents with journal-linked accounting truth.",
        status_code=StatusCode.READY,
        available_now=(
            "Draft and post invoice workflow",
            "Line-level totals with tax and discount",
            "Journal-linked posting with AR control",
        ),
        next_slice=(
            "Credit notes and adjustments",
            "AR aging and statements",
        ),
    ),
    nav_ids.CUSTOMER_RECEIPTS: PlaceholderPageModel(
        nav_id=nav_ids.CUSTOMER_RECEIPTS,
        title="Customer Receipts",
        summary="Record customer payments, allocate against open invoices, and post receipt entries with journal-linked accounting truth.",
        status_code=StatusCode.READY,
        available_now=(
            "Draft and post receipt workflow",
            "Invoice allocation with balance tracking",
            "Journal-linked posting with AR control",
        ),
        next_slice=(
            "Unallocated receipt management",
            "Multi-currency settlement",
        ),
    ),
    nav_ids.PURCHASE_BILLS: PlaceholderPageModel(
        nav_id=nav_ids.PURCHASE_BILLS,
        title="Purchase Bills",
        summary="Create, review, and post purchase bills as controlled source documents with journal-linked accounting truth.",
        status_code=StatusCode.READY,
        available_now=(
            "Draft and post bill workflow",
            "Line-level totals with tax",
            "Journal-linked posting with AP control",
        ),
        next_slice=(
            "Debit notes and adjustments",
            "AP aging and statements",
        ),
    ),
    nav_ids.SUPPLIER_PAYMENTS: PlaceholderPageModel(
        nav_id=nav_ids.SUPPLIER_PAYMENTS,
        title="Supplier Payments",
        summary="Record supplier payments, allocate against open bills, and post payment entries with journal-linked accounting truth.",
        status_code=StatusCode.READY,
        available_now=(
            "Draft and post payment workflow",
            "Bill allocation with balance tracking",
            "Journal-linked posting with AP control",
        ),
        next_slice=(
            "Unallocated payment management",
            "Multi-currency settlement",
        ),
    ),
    nav_ids.FINANCIAL_ACCOUNTS: PlaceholderPageModel(
        nav_id=nav_ids.FINANCIAL_ACCOUNTS,
        title="Financial Accounts",
        summary="Manage bank and cash accounts linked to GL accounts for treasury operations.",
        status_code=StatusCode.READY,
        available_now=(
            "Company-scoped account list",
            "Create and edit with GL linking",
            "Active/inactive status control",
        ),
        next_slice=(
            "Account balance summaries",
            "Multi-currency accounts",
        ),
    ),
    nav_ids.TREASURY_TRANSACTIONS: PlaceholderPageModel(
        nav_id=nav_ids.TREASURY_TRANSACTIONS,
        title="Treasury Transactions",
        summary="Record cash receipts, cash payments, bank receipts, and bank payments with journal-linked posting.",
        status_code=StatusCode.READY,
        available_now=(
            "Draft and post transaction workflow",
            "Multi-line transactions with account allocation",
            "Journal-linked posting per transaction type",
        ),
        next_slice=(
            "Recurring transaction templates",
            "Batch transaction processing",
        ),
    ),
    nav_ids.TREASURY_TRANSFERS: PlaceholderPageModel(
        nav_id=nav_ids.TREASURY_TRANSFERS,
        title="Treasury Transfers",
        summary="Transfer funds between financial accounts with journal-linked posting.",
        status_code=StatusCode.READY,
        available_now=(
            "Draft and post transfer workflow",
            "Inter-account transfer with GL entries",
            "Journal-linked posting",
        ),
        next_slice=(
            "Multi-currency transfers",
            "Transfer fee handling",
        ),
    ),
    nav_ids.STATEMENT_LINES: PlaceholderPageModel(
        nav_id=nav_ids.STATEMENT_LINES,
        title="Bank Statements",
        summary="Import bank statements from CSV files and manage statement lines for reconciliation.",
        status_code=StatusCode.READY,
        available_now=(
            "CSV statement import",
            "Manual statement line entry",
            "Import batch tracking",
        ),
        next_slice=(
            "OFX/QIF import formats",
            "Duplicate detection",
        ),
    ),
    nav_ids.BANK_RECONCILIATION: PlaceholderPageModel(
        nav_id=nav_ids.BANK_RECONCILIATION,
        title="Bank Reconciliation",
        summary="Reconcile bank statement lines against treasury transactions, receipts, payments, and transfers.",
        status_code=StatusCode.READY,
        available_now=(
            "Reconciliation session management",
            "Match statement lines to transactions",
            "Session completion workflow",
        ),
        next_slice=(
            "Auto-matching suggestions",
            "Reconciliation reporting",
        ),
    ),
    nav_ids.UOM_CATEGORIES: PlaceholderPageModel(
        nav_id=nav_ids.UOM_CATEGORIES,
        title="UoM Categories",
        summary="Group related units of measure for inter-unit conversion.",
        status_code=StatusCode.READY,
        available_now=(
            "Create and edit UoM categories",
            "Company-scoped reference table",
        ),
        next_slice=(),
    ),
    nav_ids.UNITS_OF_MEASURE: PlaceholderPageModel(
        nav_id=nav_ids.UNITS_OF_MEASURE,
        title="Units of Measure",
        summary="Manage unit-of-measure codes used on item master records.",
        status_code=StatusCode.READY,
        available_now=(
            "Create and edit UoM codes",
            "Company-scoped reference table",
            "Category assignment and ratio-to-base conversion",
        ),
        next_slice=(),
    ),
    nav_ids.ITEM_CATEGORIES: PlaceholderPageModel(
        nav_id=nav_ids.ITEM_CATEGORIES,
        title="Item Categories",
        summary="Group stock, non-stock, and service items by category for filtering and reporting.",
        status_code=StatusCode.READY,
        available_now=(
            "Create and edit item categories",
            "Company-scoped reference table",
        ),
        next_slice=(
            "Category-level reporting",
        ),
    ),
    nav_ids.INVENTORY_LOCATIONS: PlaceholderPageModel(
        nav_id=nav_ids.INVENTORY_LOCATIONS,
        title="Inventory Locations",
        summary="Define warehouse locations and bins for inventory document tracking.",
        status_code=StatusCode.READY,
        available_now=(
            "Create and edit inventory locations",
            "Company-scoped reference table",
        ),
        next_slice=(
            "Location-level stock reporting",
        ),
    ),
    nav_ids.ITEMS: PlaceholderPageModel(
        nav_id=nav_ids.ITEMS,
        title="Items",
        summary="Manage stock, non-stock, and service items with costing method configuration and account mapping.",
        status_code=StatusCode.READY,
        available_now=(
            "Item master CRUD with stock/non-stock/service types",
            "Weighted average costing configuration",
            "Account mapping for inventory, COGS, expense, revenue",
        ),
        next_slice=(
            "Item categories and grouping",
            "Barcode and extended attributes",
        ),
    ),
    nav_ids.INVENTORY_DOCUMENTS: PlaceholderPageModel(
        nav_id=nav_ids.INVENTORY_DOCUMENTS,
        title="Inventory Documents",
        summary="Create and post inventory receipts, issues, and adjustments with journal-linked accounting truth.",
        status_code=StatusCode.READY,
        available_now=(
            "Draft and post document workflow",
            "Receipt, issue, and adjustment types",
            "Journal-linked posting with cost layer management",
        ),
        next_slice=(
            "Purchase order integration",
            "Sales order integration",
        ),
    ),
    nav_ids.STOCK_POSITION: PlaceholderPageModel(
        nav_id=nav_ids.STOCK_POSITION,
        title="Stock Position",
        summary="View current stock on hand, valuation, and low-stock alerts derived from cost layers.",
        status_code=StatusCode.READY,
        available_now=(
            "Per-item stock position with weighted average cost",
            "Total inventory valuation summary",
            "Low-stock indicator based on reorder levels",
        ),
        next_slice=(
            "Stock movement history",
            "Valuation reports",
        ),
    ),
    nav_ids.ASSET_CATEGORIES: PlaceholderPageModel(
        nav_id=nav_ids.ASSET_CATEGORIES,
        title="Asset Categories",
        summary="Define asset categories with account mapping and default depreciation settings.",
        status_code=StatusCode.READY,
        available_now=(
            "Create and edit asset categories",
            "Account mapping for asset, accumulated depreciation, depreciation expense",
            "Default useful life and depreciation method",
        ),
        next_slice=(
            "Category reporting",
        ),
    ),
    nav_ids.ASSETS: PlaceholderPageModel(
        nav_id=nav_ids.ASSETS,
        title="Asset Register",
        summary="Manage fixed assets, track depreciation status, and preview depreciation schedules.",
        status_code=StatusCode.READY,
        available_now=(
            "Create and edit fixed assets",
            "Acquisition cost, salvage value, and useful life",
            "Depreciation schedule preview",
        ),
        next_slice=(
            "Disposal workflow",
            "Asset revaluation",
        ),
    ),
    nav_ids.DEPRECIATION_RUNS: PlaceholderPageModel(
        nav_id=nav_ids.DEPRECIATION_RUNS,
        title="Depreciation Runs",
        summary="Generate and post monthly depreciation runs. Each posted run creates a journal entry.",
        status_code=StatusCode.READY,
        available_now=(
            "Generate draft depreciation runs per period",
            "Review per-asset depreciation lines",
            "Post run to create GL journal entry",
        ),
        next_slice=(
            "Bulk run management",
            "Depreciation reporting",
        ),
    ),
    nav_ids.CONTRACTS: PlaceholderPageModel(
        nav_id=nav_ids.CONTRACTS,
        title="Contracts",
        summary="Create and manage contract master records for the active company.",
        status_code=StatusCode.READY,
        available_now=(
            "Create and edit contracts",
            "Customer and currency assignment",
            "Status lifecycle: draft, active, on hold, completed, closed, cancelled",
        ),
        next_slice=(
            "Change orders",
            "Contract billing and revenue recognition",
        ),
    ),
    nav_ids.PROJECTS: PlaceholderPageModel(
        nav_id=nav_ids.PROJECTS,
        title="Projects",
        summary="Create and manage project master records for the active company.",
        status_code=StatusCode.READY,
        available_now=(
            "Create and edit projects",
            "Link to contracts and customers",
            "Budget control mode assignment",
        ),
        next_slice=(
            "Cost codes and budgets",
            "Project cost reporting",
        ),
    ),
    nav_ids.PAYROLL_SETUP: PlaceholderPageModel(
        nav_id=nav_ids.PAYROLL_SETUP,
        title="Payroll Setup",
        summary="Configure company payroll settings, manage employees, define payroll components, and maintain effective-dated statutory rule sets.",
        status_code=StatusCode.READY,
        available_now=(
            "Company payroll configuration and Cameroon statutory pack seeding",
            "Employee master records with department and position assignment",
            "Payroll component definitions (earnings, deductions, contributions)",
            "Effective-dated payroll rule sets with bracket line maintenance",
        ),
        next_slice=(
            "Employee compensation profiles and component assignments",
            "Payroll run processing and calculation engine",
            "Payslip generation and payroll journal posting",
        ),
    ),
    nav_ids.PAYROLL_CALCULATION: PlaceholderPageModel(
        nav_id=nav_ids.PAYROLL_CALCULATION,
        title="Payroll Runs",
        summary="Manage employee compensation profiles, recurring component assignments, variable inputs, and run the calculation engine to produce payslip data.",
        status_code=StatusCode.READY,
        available_now=(
            "Employee compensation profiles (salary, effective dates)",
            "Recurring payroll component assignments per employee",
            "Variable input batches (bonuses, overtime, etc.)",
            "Payroll run creation, calculation, approval, and void",
            "Per-employee payroll detail and payslip preview",
        ),
        next_slice=(
            "GL journal posting from approved payroll runs",
            "Payment batch generation",
            "Payroll liability remittance tracking",
        ),
    ),
    nav_ids.PAYROLL_ACCOUNTING: PlaceholderPageModel(
        nav_id=nav_ids.PAYROLL_ACCOUNTING,
        title="Payroll Accounting",
        summary="Post approved payroll runs to the GL, track employee net-pay settlements, manage statutory remittance batches (DGI, CNPS), and view period-level payroll exposure summaries.",
        status_code=StatusCode.READY,
        available_now=(
            "Post approved/calculated runs to the GL as a balanced journal entry",
            "View posting detail and GL journal entry linkage",
            "Record employee net-pay settlement payments",
            "Track paid / partial / unpaid status per employee",
            "Create and manage statutory remittance batches (DGI, CNPS, other)",
            "Add detail lines to remittance batches",
            "Period-level payroll exposure summary (net pay + statutory)",
        ),
        next_slice=(),
    ),
    nav_ids.PAYROLL_OPERATIONS: PlaceholderPageModel(
        nav_id=nav_ids.PAYROLL_OPERATIONS,
        title="Payroll Operations",
        summary="Validation dashboard, statutory pack management, CSV imports, payslip and summary printing, and audit log.",
        status_code=StatusCode.READY,
        available_now=(
            "Comprehensive payroll readiness validation dashboard",
            "Statutory pack version listing and rollover",
            "CSV import for departments, positions, and employees",
            "Print payslips and payroll summary reports (QPrinter / PDF)",
            "Read-only payroll audit event log",
        ),
        next_slice=(),
    ),
    nav_ids.REPORTS: PlaceholderPageModel(
        nav_id=nav_ids.REPORTS,
        title="Reports",
        summary="Financial reports workspace with Trial Balance, General Ledger, Income Statements, Balance Sheet, Operational Reports, Analytics, and Insights.",
        status_code=StatusCode.READY,
        available_now=(
            "Trial Balance (opening/period/closing with totals)",
            "General Ledger with running balance and journal drilldown",
            "Company and fiscal context strip + shared filter bar",
            "Income Statements tab with OHADA and IAS launch tiles",
            "Print-preview and template-preview hooks",
            "Drilldown from Trial Balance to General Ledger",
        ),
        next_slice=(
            "OHADA income statement engine (SYSCOHADA Rev. 2017)",
            "IAS income statement mapping builder (IAS 1 / IFRS)",
            "Balance sheet and operational report engines",
        ),
    ),
    nav_ids.PROJECT_VARIANCE_ANALYSIS: PlaceholderPageModel(
        nav_id=nav_ids.PROJECT_VARIANCE_ANALYSIS,
        title="Project Variance Analysis",
        summary="Budget control, variance breakdown by cost code or job, and cost trend analysis for the selected project.",
        status_code=StatusCode.READY,
        available_now=(
            "KPI summary band with 9 key metrics",
            "Waterfall budget control bridge chart",
            "Horizontal variance bar charts by cost code and job",
            "Cumulative cost and revenue trend line chart",
            "Drilldown variance table with status indicators",
        ),
        next_slice=(),
    ),
    nav_ids.CONTRACT_SUMMARY: PlaceholderPageModel(
        nav_id=nav_ids.CONTRACT_SUMMARY,
        title="Contract Summary",
        summary="Financial summary and linked-project rollup for the selected contract.",
        status_code=StatusCode.READY,
        available_now=(
            "Contract financial header with derived current amount",
            "Cross-project totals for revenue, cost, commitments, budget, margin",
            "Linked project rollup table with per-project financials",
        ),
        next_slice=(),
    ),
    nav_ids.ADMINISTRATION: PlaceholderPageModel(
        nav_id=nav_ids.ADMINISTRATION,
        title="Administration",
        summary="User administration and access controls will be managed from this workspace.",
        status_code=StatusCode.PLACEHOLDER,
        available_now=(
            "Reserved administration route",
            "Current user visible in shell",
        ),
        next_slice=(
            "Users and role setup",
            "Company access controls",
        ),
    ),
    nav_ids.ROLES: PlaceholderPageModel(
        nav_id=nav_ids.ROLES,
        title="Roles",
        summary="Manage roles and assign permissions to control user access.",
        status_code=StatusCode.PLACEHOLDER,
        available_now=(
            "Role CRUD",
            "Permission assignment with cascading module checkboxes",
        ),
        next_slice=(),
    ),
    nav_ids.AUDIT_LOG: PlaceholderPageModel(
        nav_id=nav_ids.AUDIT_LOG,
        title="Audit Log",
        summary="Browse the chronological audit trail of user actions and data changes across all modules.",
        status_code=StatusCode.READY,
        available_now=(
            "Chronological audit event log with pagination",
            "Module, date range, and actor filtering",
            "Full-text search across event descriptions",
        ),
        next_slice=(),
    ),
    nav_ids.BACKUP_RESTORE: PlaceholderPageModel(
        nav_id=nav_ids.BACKUP_RESTORE,
        title="Backup & Restore",
        summary="Export an encrypted backup of all company data and import it on another machine.",
        status_code=StatusCode.READY,
        available_now=(
            "Full-system AES-256 encrypted export",
            "Merge import with conflict resolution",
        ),
        next_slice=(),
    ),
    # ── Phase 3 entity detail workspaces ────────────────────────────────
    nav_ids.CUSTOMER_DETAIL: PlaceholderPageModel(
        nav_id=nav_ids.CUSTOMER_DETAIL,
        title="Customer Detail",
        summary="Full customer workspace — receivables activity, open invoices, receipts, and account information.",
        status_code=StatusCode.READY,
        available_now=(
            "Customer header with KPI summary",
            "Invoice and receipt history",
            "Customer info and contact details",
        ),
        next_slice=(
            "Statement generation",
            "Credit note history",
        ),
    ),
    nav_ids.SUPPLIER_DETAIL: PlaceholderPageModel(
        nav_id=nav_ids.SUPPLIER_DETAIL,
        title="Supplier Detail",
        summary="Full supplier workspace — payables activity, open bills, payments, and account information.",
        status_code=StatusCode.READY,
        available_now=(
            "Supplier header with KPI summary",
            "Bill and payment history",
            "Supplier info and contact details",
        ),
        next_slice=(
            "Remittance advice",
            "Purchase order history",
        ),
    ),
    nav_ids.ACCOUNT_DETAIL: PlaceholderPageModel(
        nav_id=nav_ids.ACCOUNT_DETAIL,
        title="Account Detail",
        summary="Full account workspace — chart of accounts context, account configuration, and posting information.",
        status_code=StatusCode.READY,
        available_now=(
            "Account header with type and class context",
            "Account configuration and mapping details",
        ),
        next_slice=(
            "Posted transaction ledger",
            "Period-level balance history",
        ),
    ),
    nav_ids.ITEM_DETAIL: PlaceholderPageModel(
        nav_id=nav_ids.ITEM_DETAIL,
        title="Item Detail",
        summary="Full inventory item workspace — stock position, valuation, and item configuration.",
        status_code=StatusCode.READY,
        available_now=(
            "Item header with stock and valuation KPIs",
            "Item configuration and accounting mappings",
        ),
        next_slice=(
            "Stock movement history",
            "Open sales and purchase order lines",
        ),
    ),
    # ── Phase 5 document detail workspaces ──────────────────────────────
    nav_ids.SALES_INVOICE_DETAIL: PlaceholderPageModel(
        nav_id=nav_ids.SALES_INVOICE_DETAIL,
        title="Sales Invoice Detail",
        summary="Full invoice workspace — line items, amounts, and posting context.",
        status_code=StatusCode.READY,
        available_now=(
            "Invoice header with totals and payment status",
            "Line items with quantities, prices, and tax",
            "Document metadata and journal entry reference",
        ),
        next_slice=(
            "Receipt allocation history",
            "Credit note links",
        ),
    ),
    nav_ids.PURCHASE_BILL_DETAIL: PlaceholderPageModel(
        nav_id=nav_ids.PURCHASE_BILL_DETAIL,
        title="Purchase Bill Detail",
        summary="Full bill workspace — line items, amounts, and posting context.",
        status_code=StatusCode.READY,
        available_now=(
            "Bill header with totals and payment status",
            "Line items with quantities, costs, and tax",
            "Document metadata and journal entry reference",
        ),
        next_slice=(
            "Payment allocation history",
            "Purchase order links",
        ),
    ),
}
