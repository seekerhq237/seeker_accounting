from __future__ import annotations

from dataclasses import dataclass

from seeker_accounting.modules.payroll.payroll_permissions import ALL_PAYROLL_PERMISSIONS


@dataclass(frozen=True, slots=True)
class PermissionDefinition:
    code: str
    name: str
    module_code: str
    description: str


@dataclass(frozen=True, slots=True)
class RoleDefinition:
    code: str
    name: str
    description: str
    permission_codes: tuple[str, ...]


def _permission(code: str, name: str, module_code: str, description: str) -> PermissionDefinition:
    return PermissionDefinition(
        code=code,
        name=name,
        module_code=module_code,
        description=description,
    )


def _merge_permission_codes(*groups: tuple[str, ...]) -> tuple[str, ...]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for code in group:
            if code in seen:
                continue
            merged.append(code)
            seen.add(code)
    return tuple(merged)


def _permission_codes_with_prefix(*prefixes: str) -> tuple[str, ...]:
    return tuple(
        permission.code
        for permission in ALL_SYSTEM_PERMISSIONS
        if any(permission.code.startswith(prefix) for prefix in prefixes)
    )


def _permission_codes_with_suffix(*suffixes: str) -> tuple[str, ...]:
    return tuple(
        permission.code
        for permission in ALL_SYSTEM_PERMISSIONS
        if any(permission.code.endswith(suffix) for suffix in suffixes)
    )


COMPANY_PERMISSION_DEFINITIONS: tuple[PermissionDefinition, ...] = (
    _permission("companies.view", "View Companies", "companies", "View company records and their current operating status."),
    _permission("companies.create", "Create Companies", "companies", "Register new companies in the application."),
    _permission("companies.edit", "Edit Companies", "companies", "Edit company master data and contact details."),
    _permission("companies.deactivate", "Deactivate Companies", "companies", "Deactivate companies and block them from being selected."),
    _permission("companies.delete", "Delete Companies", "companies", "Permanently delete companies when a controlled deletion workflow is introduced."),
    _permission("companies.select_active", "Select Active Company", "companies", "Select the active company context for the current session."),
    _permission("companies.preferences.manage", "Manage Company Preferences", "companies", "Change company operational preferences and formatting defaults."),
    _permission("companies.fiscal_defaults.manage", "Manage Fiscal Defaults", "companies", "Change company fiscal-year defaults and posting grace settings."),
    _permission("companies.project_preferences.manage", "Manage Project Preferences", "companies", "Change company project-control preferences."),
    _permission("companies.chart.seed", "Seed Company Chart", "companies", "Seed a company chart of accounts during setup or recovery workflows."),
)

CHART_PERMISSION_DEFINITIONS: tuple[PermissionDefinition, ...] = (
    _permission("chart.accounts.view", "View Chart Of Accounts", "chart", "View company chart accounts and hierarchy."),
    _permission("chart.accounts.create", "Create Accounts", "chart", "Create accounts in the company chart of accounts."),
    _permission("chart.accounts.edit", "Edit Accounts", "chart", "Edit chart account details and hierarchy placement."),
    _permission("chart.accounts.deactivate", "Deactivate Accounts", "chart", "Deactivate chart accounts to prevent operational use."),
    _permission("chart.accounts.delete", "Delete Accounts", "chart", "Delete chart accounts if a controlled delete workflow is introduced later."),
    _permission("chart.import", "Import Chart Templates", "chart", "Import external or built-in chart templates into a company chart."),
    _permission("chart.seed", "Seed Built-In Chart", "chart", "Seed a company chart using the built-in template catalog."),
    _permission("chart.role_mappings.view", "View Account Role Mappings", "chart", "View account role mappings used by posting controls."),
    _permission("chart.role_mappings.manage", "Manage Account Role Mappings", "chart", "Create and update account role mappings used by operational posting services."),
)

FISCAL_PERMISSION_DEFINITIONS: tuple[PermissionDefinition, ...] = (
    _permission("fiscal.years.view", "View Fiscal Years", "fiscal", "View company fiscal years and period calendars."),
    _permission("fiscal.years.create", "Create Fiscal Years", "fiscal", "Create new fiscal years for a company."),
    _permission("fiscal.years.edit", "Edit Fiscal Years", "fiscal", "Edit fiscal year definitions before downstream use."),
    _permission("fiscal.years.deactivate", "Deactivate Fiscal Years", "fiscal", "Deactivate fiscal years when a controlled deactivation flow is available."),
    _permission("fiscal.periods.view", "View Fiscal Periods", "fiscal", "View fiscal periods and current open, closed, or locked states."),
    _permission("fiscal.periods.generate", "Generate Fiscal Periods", "fiscal", "Generate fiscal periods from a fiscal year definition."),
    _permission("fiscal.periods.open", "Open Fiscal Periods", "fiscal", "Open fiscal periods for posting."),
    _permission("fiscal.periods.close", "Close Fiscal Periods", "fiscal", "Close fiscal periods to block normal posting."),
    _permission("fiscal.periods.reopen", "Reopen Fiscal Periods", "fiscal", "Reopen previously closed fiscal periods."),
    _permission("fiscal.periods.lock", "Lock Fiscal Periods", "fiscal", "Lock fiscal periods to prevent further operational changes."),
)

JOURNAL_PERMISSION_DEFINITIONS: tuple[PermissionDefinition, ...] = (
    _permission("journals.view", "View Journals", "journals", "View journal entries and journal lines."),
    _permission("journals.create", "Create Draft Journals", "journals", "Create draft manual journal entries."),
    _permission("journals.edit", "Edit Draft Journals", "journals", "Edit draft manual journal entries before posting."),
    _permission("journals.delete", "Delete Draft Journals", "journals", "Delete draft journals if a controlled delete workflow is introduced."),
    _permission("journals.post", "Post Journals", "journals", "Post balanced journal entries to the general ledger."),
    _permission("journals.reverse", "Reverse Journals", "journals", "Create controlled reversing entries when a reversal workflow is introduced."),
)

REFERENCE_PERMISSION_DEFINITIONS: tuple[PermissionDefinition, ...] = (
    _permission("reference.payment_terms.view", "View Payment Terms", "reference", "View payment terms used across customer and supplier workflows."),
    _permission("reference.payment_terms.create", "Create Payment Terms", "reference", "Create payment term records."),
    _permission("reference.payment_terms.edit", "Edit Payment Terms", "reference", "Edit payment term records."),
    _permission("reference.payment_terms.deactivate", "Deactivate Payment Terms", "reference", "Deactivate payment terms."),
    _permission("reference.tax_codes.view", "View Tax Codes", "reference", "View tax codes and tax configuration."),
    _permission("reference.tax_codes.create", "Create Tax Codes", "reference", "Create tax codes."),
    _permission("reference.tax_codes.edit", "Edit Tax Codes", "reference", "Edit tax codes."),
    _permission("reference.tax_codes.deactivate", "Deactivate Tax Codes", "reference", "Deactivate tax codes."),
    _permission("reference.tax_mappings.view", "View Tax Mappings", "reference", "View tax code account mappings."),
    _permission("reference.tax_mappings.manage", "Manage Tax Mappings", "reference", "Create and update tax code account mappings."),
    _permission("reference.document_sequences.view", "View Document Sequences", "reference", "View document numbering sequences."),
    _permission("reference.document_sequences.create", "Create Document Sequences", "reference", "Create document numbering sequences."),
    _permission("reference.document_sequences.edit", "Edit Document Sequences", "reference", "Edit document numbering sequences."),
    _permission("reference.document_sequences.deactivate", "Deactivate Document Sequences", "reference", "Deactivate document numbering sequences."),
    _permission("reference.document_sequences.preview", "Preview Document Sequences", "reference", "Preview generated document numbers from a numbering sequence."),
    _permission("reference.account_role_mappings.view", "View Account Role Mappings", "reference", "View operational account role mappings."),
    _permission("reference.account_role_mappings.manage", "Manage Account Role Mappings", "reference", "Create and update operational account role mappings."),
)

CUSTOMER_PERMISSION_DEFINITIONS: tuple[PermissionDefinition, ...] = (
    _permission("customers.view", "View Customers", "customers", "View customer master records."),
    _permission("customers.create", "Create Customers", "customers", "Create customer records."),
    _permission("customers.edit", "Edit Customers", "customers", "Edit customer records."),
    _permission("customers.deactivate", "Deactivate Customers", "customers", "Deactivate customer records."),
    _permission("customers.delete", "Delete Customers", "customers", "Delete customer records when a controlled delete workflow is introduced."),
    _permission("customers.groups.view", "View Customer Groups", "customers", "View customer groups."),
    _permission("customers.groups.create", "Create Customer Groups", "customers", "Create customer groups."),
    _permission("customers.groups.edit", "Edit Customer Groups", "customers", "Edit customer groups."),
    _permission("customers.groups.deactivate", "Deactivate Customer Groups", "customers", "Deactivate customer groups."),
    _permission("customers.groups.delete", "Delete Customer Groups", "customers", "Delete customer groups when a controlled delete workflow is introduced."),
)

SUPPLIER_PERMISSION_DEFINITIONS: tuple[PermissionDefinition, ...] = (
    _permission("suppliers.view", "View Suppliers", "suppliers", "View supplier master records."),
    _permission("suppliers.create", "Create Suppliers", "suppliers", "Create supplier records."),
    _permission("suppliers.edit", "Edit Suppliers", "suppliers", "Edit supplier records."),
    _permission("suppliers.deactivate", "Deactivate Suppliers", "suppliers", "Deactivate supplier records."),
    _permission("suppliers.delete", "Delete Suppliers", "suppliers", "Delete supplier records when a controlled delete workflow is introduced."),
    _permission("suppliers.groups.view", "View Supplier Groups", "suppliers", "View supplier groups."),
    _permission("suppliers.groups.create", "Create Supplier Groups", "suppliers", "Create supplier groups."),
    _permission("suppliers.groups.edit", "Edit Supplier Groups", "suppliers", "Edit supplier groups."),
    _permission("suppliers.groups.deactivate", "Deactivate Supplier Groups", "suppliers", "Deactivate supplier groups."),
    _permission("suppliers.groups.delete", "Delete Supplier Groups", "suppliers", "Delete supplier groups when a controlled delete workflow is introduced."),
)

SALES_PERMISSION_DEFINITIONS: tuple[PermissionDefinition, ...] = (
    _permission("sales.invoices.view", "View Sales Invoices", "sales", "View sales invoices and their status."),
    _permission("sales.invoices.create", "Create Sales Invoices", "sales", "Create draft sales invoices."),
    _permission("sales.invoices.edit", "Edit Sales Invoices", "sales", "Edit draft sales invoices."),
    _permission("sales.invoices.cancel", "Cancel Sales Invoices", "sales", "Cancel draft sales invoices."),
    _permission("sales.invoices.delete", "Delete Sales Invoices", "sales", "Delete sales invoices when a controlled delete workflow is introduced."),
    _permission("sales.invoices.post", "Post Sales Invoices", "sales", "Post sales invoices to receivables and revenue journals."),
    _permission("sales.invoices.export", "Export Sales Invoices", "sales", "Export sales invoice data."),
    _permission("sales.invoices.print", "Print Sales Invoices", "sales", "Print or render sales invoices for issue."),
    _permission("sales.quotes.view", "View Customer Quotes", "sales", "View customer quotes and estimates."),
    _permission("sales.quotes.create", "Create Customer Quotes", "sales", "Create draft customer quotes."),
    _permission("sales.quotes.edit", "Edit Customer Quotes", "sales", "Edit draft customer quotes."),
    _permission("sales.quotes.issue", "Issue Customer Quotes", "sales", "Issue quotes to customers, locking them for review."),
    _permission("sales.quotes.accept", "Accept Customer Quotes", "sales", "Mark issued quotes as accepted by the customer."),
    _permission("sales.quotes.reject", "Reject Customer Quotes", "sales", "Mark issued quotes as rejected by the customer."),
    _permission("sales.quotes.cancel", "Cancel Customer Quotes", "sales", "Cancel draft or issued customer quotes."),
    _permission("sales.quotes.convert", "Convert Customer Quotes", "sales", "Convert accepted quotes into draft sales invoices."),
    _permission("sales.quotes.print", "Print Customer Quotes", "sales", "Print or render customer quotes for issue."),
    _permission("sales.orders.view", "View Sales Orders", "sales", "View sales orders and their status."),
    _permission("sales.orders.create", "Create Sales Orders", "sales", "Create draft sales orders."),
    _permission("sales.orders.edit", "Edit Sales Orders", "sales", "Edit draft sales orders."),
    _permission("sales.orders.confirm", "Confirm Sales Orders", "sales", "Confirm sales orders, locking them for editing."),
    _permission("sales.orders.cancel", "Cancel Sales Orders", "sales", "Cancel draft or confirmed sales orders."),
    _permission("sales.orders.convert", "Convert Sales Orders", "sales", "Convert confirmed orders into draft sales invoices."),
    _permission("sales.orders.print", "Print Sales Orders", "sales", "Print or render sales order documents."),
    _permission("sales.credit_notes.view", "View Sales Credit Notes", "sales", "View sales credit notes and their lines."),
    _permission("sales.credit_notes.create", "Create Sales Credit Notes", "sales", "Create draft sales credit notes."),
    _permission("sales.credit_notes.edit", "Edit Sales Credit Notes", "sales", "Edit draft sales credit notes."),
    _permission("sales.credit_notes.post", "Post Sales Credit Notes", "sales", "Post sales credit notes to the general ledger."),
    _permission("sales.credit_notes.cancel", "Cancel Sales Credit Notes", "sales", "Cancel draft sales credit notes."),
    _permission("sales.credit_notes.print", "Print Sales Credit Notes", "sales", "Print or export sales credit note documents."),
    _permission("sales.receipts.view", "View Customer Receipts", "sales", "View customer receipts and allocations."),
    _permission("sales.receipts.create", "Create Customer Receipts", "sales", "Create draft customer receipts."),
    _permission("sales.receipts.edit", "Edit Customer Receipts", "sales", "Edit draft customer receipts."),
    _permission("sales.receipts.cancel", "Cancel Customer Receipts", "sales", "Cancel draft customer receipts."),
    _permission("sales.receipts.post", "Post Customer Receipts", "sales", "Post customer receipts to cash and receivable control accounts."),
    _permission("sales.receipts.allocate", "Allocate Customer Receipts", "sales", "Allocate customer receipts against open invoices."),
    _permission("sales.receipts.export", "Export Customer Receipts", "sales", "Export customer receipt data."),
    _permission("sales.receipts.print", "Print Customer Receipts", "sales", "Print customer receipt documents."),
)

PURCHASE_PERMISSION_DEFINITIONS: tuple[PermissionDefinition, ...] = (
    _permission("purchases.orders.view", "View Purchase Orders", "purchases", "View purchase orders and their status."),
    _permission("purchases.orders.create", "Create Purchase Orders", "purchases", "Create draft purchase orders."),
    _permission("purchases.orders.edit", "Edit Purchase Orders", "purchases", "Edit draft purchase orders."),
    _permission("purchases.orders.send", "Send Purchase Orders", "purchases", "Send purchase orders to the supplier."),
    _permission("purchases.orders.acknowledge", "Acknowledge Purchase Orders", "purchases", "Mark purchase orders as acknowledged by the supplier."),
    _permission("purchases.orders.cancel", "Cancel Purchase Orders", "purchases", "Cancel draft or sent purchase orders."),
    _permission("purchases.orders.convert", "Convert Purchase Orders", "purchases", "Convert acknowledged purchase orders to purchase bills."),
    _permission("purchases.orders.print", "Print Purchase Orders", "purchases", "Print purchase order documents."),
    _permission("purchases.bills.view", "View Purchase Bills", "purchases", "View purchase bills and their status."),
    _permission("purchases.bills.create", "Create Purchase Bills", "purchases", "Create draft purchase bills."),
    _permission("purchases.bills.edit", "Edit Purchase Bills", "purchases", "Edit draft purchase bills."),
    _permission("purchases.bills.cancel", "Cancel Purchase Bills", "purchases", "Cancel draft purchase bills."),
    _permission("purchases.bills.delete", "Delete Purchase Bills", "purchases", "Delete purchase bills when a controlled delete workflow is introduced."),
    _permission("purchases.bills.post", "Post Purchase Bills", "purchases", "Post purchase bills to expense, tax, and payable accounts."),
    _permission("purchases.bills.export", "Export Purchase Bills", "purchases", "Export purchase bill data."),
    _permission("purchases.bills.print", "Print Purchase Bills", "purchases", "Print purchase bills."),
    _permission("purchases.payments.view", "View Supplier Payments", "purchases", "View supplier payments and allocations."),
    _permission("purchases.payments.create", "Create Supplier Payments", "purchases", "Create draft supplier payments."),
    _permission("purchases.payments.edit", "Edit Supplier Payments", "purchases", "Edit draft supplier payments."),
    _permission("purchases.payments.cancel", "Cancel Supplier Payments", "purchases", "Cancel draft supplier payments."),
    _permission("purchases.payments.post", "Post Supplier Payments", "purchases", "Post supplier payments to cash and payable control accounts."),
    _permission("purchases.payments.allocate", "Allocate Supplier Payments", "purchases", "Allocate supplier payments against open purchase bills."),
    _permission("purchases.payments.export", "Export Supplier Payments", "purchases", "Export supplier payment data."),
    _permission("purchases.payments.print", "Print Supplier Payments", "purchases", "Print supplier payment documents."),
    _permission("purchases.credit_notes.view", "View Purchase Credit Notes", "purchases", "View purchase credit notes and their lines."),
    _permission("purchases.credit_notes.create", "Create Purchase Credit Notes", "purchases", "Create draft purchase credit notes."),
    _permission("purchases.credit_notes.edit", "Edit Purchase Credit Notes", "purchases", "Edit draft purchase credit notes."),
    _permission("purchases.credit_notes.post", "Post Purchase Credit Notes", "purchases", "Post purchase credit notes to the general ledger."),
    _permission("purchases.credit_notes.cancel", "Cancel Purchase Credit Notes", "purchases", "Cancel draft purchase credit notes."),
    _permission("purchases.credit_notes.print", "Print Purchase Credit Notes", "purchases", "Print or export purchase credit note documents."),
)

TREASURY_PERMISSION_DEFINITIONS: tuple[PermissionDefinition, ...] = (
    _permission("treasury.financial_accounts.view", "View Financial Accounts", "treasury", "View financial account master records."),
    _permission("treasury.financial_accounts.create", "Create Financial Accounts", "treasury", "Create financial account master records."),
    _permission("treasury.financial_accounts.edit", "Edit Financial Accounts", "treasury", "Edit financial account master records."),
    _permission("treasury.financial_accounts.deactivate", "Deactivate Financial Accounts", "treasury", "Deactivate financial account master records."),
    _permission("treasury.transactions.view", "View Treasury Transactions", "treasury", "View treasury transactions and their lines."),
    _permission("treasury.transactions.create", "Create Treasury Transactions", "treasury", "Create draft treasury transactions."),
    _permission("treasury.transactions.edit", "Edit Treasury Transactions", "treasury", "Edit draft treasury transactions."),
    _permission("treasury.transactions.cancel", "Cancel Treasury Transactions", "treasury", "Cancel draft treasury transactions."),
    _permission("treasury.transactions.post", "Post Treasury Transactions", "treasury", "Post treasury transactions to the general ledger."),
    _permission("treasury.transactions.export", "Export Treasury Transactions", "treasury", "Export treasury transaction data."),
    _permission("treasury.transactions.print", "Print Treasury Transactions", "treasury", "Print treasury transaction documents."),
    _permission("treasury.transfers.view", "View Treasury Transfers", "treasury", "View inter-account transfers."),
    _permission("treasury.transfers.create", "Create Treasury Transfers", "treasury", "Create draft inter-account transfers."),
    _permission("treasury.transfers.edit", "Edit Treasury Transfers", "treasury", "Edit draft inter-account transfers."),
    _permission("treasury.transfers.cancel", "Cancel Treasury Transfers", "treasury", "Cancel draft treasury transfers."),
    _permission("treasury.transfers.post", "Post Treasury Transfers", "treasury", "Post inter-account treasury transfers."),
    _permission("treasury.transfers.export", "Export Treasury Transfers", "treasury", "Export treasury transfer data."),
    _permission("treasury.transfers.print", "Print Treasury Transfers", "treasury", "Print treasury transfer documents."),
    _permission("treasury.statement_lines.view", "View Statement Lines", "treasury", "View imported and manual bank statement lines."),
    _permission("treasury.statement_lines.import", "Import Statement Lines", "treasury", "Import bank statement lines from supported file formats."),
    _permission("treasury.statement_lines.create_manual", "Create Manual Statement Lines", "treasury", "Create manual bank statement lines."),
    _permission("treasury.statement_lines.delete", "Delete Statement Lines", "treasury", "Delete statement lines when a controlled delete workflow is introduced."),
    _permission("treasury.reconciliation.view", "View Reconciliation Sessions", "treasury", "View bank reconciliation sessions and matches."),
    _permission("treasury.reconciliation.create_session", "Create Reconciliation Sessions", "treasury", "Create new bank reconciliation sessions."),
    _permission("treasury.reconciliation.match", "Match Reconciliation Lines", "treasury", "Match statement lines to operational or journal entries during reconciliation."),
    _permission("treasury.reconciliation.unmatch", "Unmatch Reconciliation Lines", "treasury", "Remove reconciliation matches before completion."),
    _permission("treasury.reconciliation.complete", "Complete Reconciliation", "treasury", "Complete and close bank reconciliation sessions."),
    _permission("treasury.reconciliation.export", "Export Reconciliation Data", "treasury", "Export bank reconciliation results."),
)

INVENTORY_PERMISSION_DEFINITIONS: tuple[PermissionDefinition, ...] = (
    _permission("inventory.units.view", "View Units Of Measure", "inventory", "View unit-of-measure records."),
    _permission("inventory.units.create", "Create Units Of Measure", "inventory", "Create unit-of-measure records."),
    _permission("inventory.units.edit", "Edit Units Of Measure", "inventory", "Edit unit-of-measure records."),
    _permission("inventory.units.deactivate", "Deactivate Units Of Measure", "inventory", "Deactivate unit-of-measure records."),
    _permission("inventory.categories.view", "View Item Categories", "inventory", "View inventory item categories."),
    _permission("inventory.categories.create", "Create Item Categories", "inventory", "Create inventory item categories."),
    _permission("inventory.categories.edit", "Edit Item Categories", "inventory", "Edit inventory item categories."),
    _permission("inventory.categories.deactivate", "Deactivate Item Categories", "inventory", "Deactivate inventory item categories."),
    _permission("inventory.locations.view", "View Inventory Locations", "inventory", "View inventory locations."),
    _permission("inventory.locations.create", "Create Inventory Locations", "inventory", "Create inventory locations."),
    _permission("inventory.locations.edit", "Edit Inventory Locations", "inventory", "Edit inventory locations."),
    _permission("inventory.locations.deactivate", "Deactivate Inventory Locations", "inventory", "Deactivate inventory locations."),
    _permission("inventory.items.view", "View Items", "inventory", "View inventory items."),
    _permission("inventory.items.create", "Create Items", "inventory", "Create inventory items."),
    _permission("inventory.items.edit", "Edit Items", "inventory", "Edit inventory items."),
    _permission("inventory.items.deactivate", "Deactivate Items", "inventory", "Deactivate inventory items."),
    _permission("inventory.documents.view", "View Inventory Documents", "inventory", "View inventory documents and lines."),
    _permission("inventory.documents.create", "Create Inventory Documents", "inventory", "Create draft inventory documents."),
    _permission("inventory.documents.edit", "Edit Inventory Documents", "inventory", "Edit draft inventory documents."),
    _permission("inventory.documents.post", "Post Inventory Documents", "inventory", "Post inventory documents to stock and general ledger balances."),
    _permission("inventory.documents.cancel", "Cancel Inventory Documents", "inventory", "Cancel draft inventory documents."),
    _permission("inventory.stock.view", "View Stock Positions", "inventory", "View stock positions and low-stock indicators."),
    _permission("inventory.valuation.view", "View Inventory Valuation", "inventory", "View inventory valuation summaries."),
    _permission("inventory.valuation.export", "Export Inventory Valuation", "inventory", "Export inventory valuation summaries and detail."),
)

ASSET_PERMISSION_DEFINITIONS: tuple[PermissionDefinition, ...] = (
    _permission("assets.categories.view", "View Asset Categories", "assets", "View fixed-asset categories and their account mappings."),
    _permission("assets.categories.create", "Create Asset Categories", "assets", "Create fixed-asset categories."),
    _permission("assets.categories.edit", "Edit Asset Categories", "assets", "Edit fixed-asset categories."),
    _permission("assets.categories.deactivate", "Deactivate Asset Categories", "assets", "Deactivate fixed-asset categories."),
    _permission("assets.master.view", "View Assets", "assets", "View fixed asset master records."),
    _permission("assets.master.create", "Create Assets", "assets", "Create fixed asset master records."),
    _permission("assets.master.edit", "Edit Assets", "assets", "Edit draft or eligible asset master records."),
    _permission("assets.master.activate", "Activate Assets", "assets", "Activate draft assets for depreciation processing."),
    _permission("assets.master.dispose", "Dispose Assets", "assets", "Dispose fixed assets through the controlled asset lifecycle."),
    _permission("assets.master.delete", "Delete Assets", "assets", "Delete fixed assets when a controlled delete workflow is introduced."),
    _permission("assets.components.manage", "Manage Asset Components", "assets", "Manage component-accounting structures on assets."),
    _permission("assets.settings.manage", "Manage Asset Depreciation Settings", "assets", "Manage depreciation settings, pools, and depletion profiles."),
    _permission("assets.usage.manage", "Manage Asset Usage Records", "assets", "Manage asset usage records for production-based depreciation methods."),
    _permission("assets.schedule.preview", "Preview Depreciation Schedules", "assets", "Preview projected depreciation schedules before execution."),
    _permission("assets.runs.view", "View Depreciation Runs", "assets", "View depreciation run batches and results."),
    _permission("assets.runs.create", "Create Depreciation Runs", "assets", "Create depreciation runs."),
    _permission("assets.runs.cancel", "Cancel Depreciation Runs", "assets", "Cancel draft depreciation runs."),
    _permission("assets.runs.post", "Post Depreciation Runs", "assets", "Post depreciation runs to the general ledger."),
    _permission("assets.runs.export", "Export Depreciation Runs", "assets", "Export depreciation run details."),
)

CONTRACT_PERMISSION_DEFINITIONS: tuple[PermissionDefinition, ...] = (
    _permission("contracts.view", "View Contracts", "contracts", "View contract master records."),
    _permission("contracts.create", "Create Contracts", "contracts", "Create contract master records."),
    _permission("contracts.edit", "Edit Contracts", "contracts", "Edit contracts."),
    _permission("contracts.close", "Close Contracts", "contracts", "Close contracts through the controlled contract lifecycle."),
    _permission("contracts.delete", "Delete Contracts", "contracts", "Delete contracts when a controlled delete workflow is introduced."),
    _permission("projects.view", "View Projects", "projects", "View project master records."),
    _permission("projects.create", "Create Projects", "projects", "Create project master records."),
    _permission("projects.edit", "Edit Projects", "projects", "Edit projects."),
    _permission("projects.close", "Close Projects", "projects", "Close projects through the controlled project lifecycle."),
    _permission("projects.delete", "Delete Projects", "projects", "Delete projects when a controlled delete workflow is introduced."),
    _permission("projects.change_orders.view", "View Change Orders", "projects", "View contract change orders."),
    _permission("projects.change_orders.create", "Create Change Orders", "projects", "Create contract change orders."),
    _permission("projects.change_orders.edit", "Edit Change Orders", "projects", "Edit draft change orders."),
    _permission("projects.change_orders.submit", "Submit Change Orders", "projects", "Submit change orders for approval."),
    _permission("projects.change_orders.approve", "Approve Change Orders", "projects", "Approve contract change orders."),
    _permission("projects.change_orders.reject", "Reject Change Orders", "projects", "Reject contract change orders."),
    _permission("projects.structure.jobs.manage", "Manage Project Jobs", "projects", "Manage project job structures."),
    _permission("projects.structure.cost_codes.manage", "Manage Project Cost Codes", "projects", "Manage project cost codes."),
)

JOB_COSTING_PERMISSION_DEFINITIONS: tuple[PermissionDefinition, ...] = (
    _permission("job_costing.commitments.view", "View Project Commitments", "job_costing", "View project commitments and their workflow state."),
    _permission("job_costing.commitments.create", "Create Project Commitments", "job_costing", "Create project commitments."),
    _permission("job_costing.commitments.edit", "Edit Project Commitments", "job_costing", "Edit draft project commitments."),
    _permission("job_costing.commitments.submit", "Submit Project Commitments", "job_costing", "Submit project commitments for approval."),
    _permission("job_costing.commitments.approve", "Approve Project Commitments", "job_costing", "Approve project commitments."),
    _permission("job_costing.commitments.reject", "Reject Project Commitments", "job_costing", "Reject project commitments."),
    _permission("job_costing.actual_costs.view", "View Project Actual Costs", "job_costing", "View posted project actual costs."),
    _permission("job_costing.profitability.view", "View Project Profitability", "job_costing", "View project profitability analysis."),
    _permission("job_costing.profitability.export", "Export Project Profitability", "job_costing", "Export project profitability analysis."),
)

BUDGET_PERMISSION_DEFINITIONS: tuple[PermissionDefinition, ...] = (
    _permission("budgets.view", "View Project Budgets", "budgets", "View project budgets and versions."),
    _permission("budgets.create", "Create Project Budgets", "budgets", "Create project budget versions."),
    _permission("budgets.edit", "Edit Project Budgets", "budgets", "Edit draft project budget versions."),
    _permission("budgets.submit", "Submit Project Budgets", "budgets", "Submit project budgets for approval."),
    _permission("budgets.approve", "Approve Project Budgets", "budgets", "Approve project budget versions."),
    _permission("budgets.cancel", "Cancel Project Budgets", "budgets", "Cancel project budget versions."),
    _permission("budgets.availability.check", "Check Budget Availability", "budgets", "Run budget-availability checks before project cost commitments or postings."),
    _permission("budgets.export", "Export Project Budgets", "budgets", "Export project budget data."),
)

REPORTING_PERMISSION_DEFINITIONS: tuple[PermissionDefinition, ...] = (
    _permission("reports.trial_balance.view", "View Trial Balance", "reports", "Generate and view trial balance reports."),
    _permission("reports.trial_balance.export", "Export Trial Balance", "reports", "Export trial balance reports."),
    _permission("reports.trial_balance.print", "Print Trial Balance", "reports", "Print trial balance reports."),
    _permission("reports.general_ledger.view", "View General Ledger", "reports", "Generate and view general ledger reports."),
    _permission("reports.general_ledger.export", "Export General Ledger", "reports", "Export general ledger reports."),
    _permission("reports.general_ledger.print", "Print General Ledger", "reports", "Print general ledger reports."),
    _permission("reports.ohada_income_statement.view", "View OHADA Income Statement", "reports", "Generate and view OHADA income statement reports."),
    _permission("reports.ohada_income_statement.export", "Export OHADA Income Statement", "reports", "Export OHADA income statement reports."),
    _permission("reports.ohada_income_statement.print", "Print OHADA Income Statement", "reports", "Print OHADA income statement reports."),
    _permission("reports.ias_income_statement.view", "View IAS Income Statement", "reports", "Generate and view IAS or IFRS income statement reports."),
    _permission("reports.ias_income_statement.export", "Export IAS Income Statement", "reports", "Export IAS or IFRS income statement reports."),
    _permission("reports.ias_income_statement.print", "Print IAS Income Statement", "reports", "Print IAS or IFRS income statement reports."),
    _permission("reports.ias_templates.view", "View IAS Templates", "reports", "View IAS or IFRS template definitions."),
    _permission("reports.ias_templates.manage", "Manage IAS Templates", "reports", "Create and update IAS or IFRS template definitions."),
    _permission("reports.ias_mappings.view", "View IAS Mappings", "reports", "View IAS or IFRS account mappings."),
    _permission("reports.ias_mappings.manage", "Manage IAS Mappings", "reports", "Create and update IAS or IFRS account mappings."),
    # Balance sheet — split by framework (replaces the unified reports.balance_sheet.* codes)
    _permission("reports.ohada_balance_sheet.view", "View OHADA Balance Sheet", "reports", "Generate and view OHADA balance sheet reports."),
    _permission("reports.ohada_balance_sheet.export", "Export OHADA Balance Sheet", "reports", "Export OHADA balance sheet reports."),
    _permission("reports.ohada_balance_sheet.print", "Print OHADA Balance Sheet", "reports", "Print OHADA balance sheet reports."),
    _permission("reports.ias_balance_sheet.view", "View IAS Balance Sheet", "reports", "Generate and view IAS or IFRS balance sheet reports."),
    _permission("reports.ias_balance_sheet.export", "Export IAS Balance Sheet", "reports", "Export IAS or IFRS balance sheet reports."),
    _permission("reports.ias_balance_sheet.print", "Print IAS Balance Sheet", "reports", "Print IAS or IFRS balance sheet reports."),
    # Operational report tiles — separate access per report type
    _permission("reports.ar_aging.view", "View AR Aging", "reports", "Generate and view accounts receivable aging reports."),
    _permission("reports.ar_aging.export", "Export AR Aging", "reports", "Export accounts receivable aging reports."),
    _permission("reports.ar_aging.print", "Print AR Aging", "reports", "Print accounts receivable aging reports."),
    _permission("reports.ap_aging.view", "View AP Aging", "reports", "Generate and view accounts payable aging reports."),
    _permission("reports.ap_aging.export", "Export AP Aging", "reports", "Export accounts payable aging reports."),
    _permission("reports.ap_aging.print", "Print AP Aging", "reports", "Print accounts payable aging reports."),
    _permission("reports.customer_statements.view", "View Customer Statements", "reports", "Generate and view customer subledger statements."),
    _permission("reports.customer_statements.export", "Export Customer Statements", "reports", "Export customer subledger statements."),
    _permission("reports.customer_statements.print", "Print Customer Statements", "reports", "Print customer subledger statements."),
    _permission("reports.supplier_statements.view", "View Supplier Statements", "reports", "Generate and view supplier subledger statements."),
    _permission("reports.supplier_statements.export", "Export Supplier Statements", "reports", "Export supplier subledger statements."),
    _permission("reports.supplier_statements.print", "Print Supplier Statements", "reports", "Print supplier subledger statements."),
    _permission("reports.payroll_summary.view", "View Payroll Summary", "reports", "Generate and view payroll summary reports."),
    _permission("reports.payroll_summary.export", "Export Payroll Summary", "reports", "Export payroll summary reports."),
    _permission("reports.payroll_summary.print", "Print Payroll Summary", "reports", "Print payroll summary reports."),
    _permission("reports.treasury_reports.view", "View Treasury Reports", "reports", "Generate and view cash and bank movement reports."),
    _permission("reports.treasury_reports.export", "Export Treasury Reports", "reports", "Export cash and bank movement reports."),
    _permission("reports.treasury_reports.print", "Print Treasury Reports", "reports", "Print cash and bank movement reports."),
    # Analytics and insights workspace
    _permission("reports.financial_analysis.view", "View Financial Analysis", "reports", "Access the financial analysis and insights workspace."),
    _permission("reports.financial_analysis.export", "Export Financial Analysis", "reports", "Export financial analysis reports."),
    _permission("reports.financial_analysis.print", "Print Financial Analysis", "reports", "Print financial analysis reports."),
)

MANAGEMENT_PERMISSION_DEFINITIONS: tuple[PermissionDefinition, ...] = (
    _permission("management.contract_summary.view", "View Contract Summary", "management", "View contract summary dashboards and reports."),
    _permission("management.contract_summary.export", "Export Contract Summary", "management", "Export contract summary dashboards and reports."),
    _permission("management.project_variance.view", "View Project Variance", "management", "View project budget variance dashboards and reports."),
    _permission("management.project_variance.export", "Export Project Variance", "management", "Export project budget variance dashboards and reports."),
)

AUDIT_PERMISSION_DEFINITIONS: tuple[PermissionDefinition, ...] = (
    _permission("audit.view", "View Audit Log", "audit", "View audit event records."),
    _permission("audit.export", "Export Audit Log", "audit", "Export audit event records."),
    _permission("audit.filter", "Filter Audit Log", "audit", "Filter audit event records by actor, module, entity, and date."),
    _permission("audit.read_sensitive", "Read Sensitive Audit Details", "audit", "View sensitive audit metadata that may contain confidential operational detail."),
)

ADMINISTRATION_PERMISSION_DEFINITIONS: tuple[PermissionDefinition, ...] = (
    _permission("administration.users.view", "View Users", "administration", "View user records."),
    _permission("administration.users.create", "Create Users", "administration", "Create user accounts."),
    _permission("administration.users.edit", "Edit Users", "administration", "Edit user accounts."),
    _permission("administration.users.deactivate", "Deactivate Users", "administration", "Deactivate user accounts."),
    _permission("administration.users.delete", "Delete Users", "administration", "Delete user accounts when a controlled delete workflow is introduced."),
    _permission("administration.roles.view", "View Roles", "administration", "View role definitions."),
    _permission("administration.roles.create", "Create Roles", "administration", "Create role definitions."),
    _permission("administration.roles.edit", "Edit Roles", "administration", "Edit role definitions."),
    _permission("administration.roles.delete", "Delete Roles", "administration", "Delete role definitions when a controlled delete workflow is introduced."),
    _permission("administration.role_permissions.assign", "Assign Role Permissions", "administration", "Assign permissions to roles."),
    _permission("administration.user_roles.assign", "Assign User Roles", "administration", "Assign roles to users."),
    _permission("administration.company_access.assign", "Assign Company Access", "administration", "Grant or update user access to companies."),
    _permission("administration.permissions.view", "View Permission Catalog", "administration", "View the system permission catalog."),
    _permission("administration.backup.export", "Export System Backup", "administration", "Export an encrypted backup of the full application database and assets."),
    _permission("administration.backup.import", "Import System Backup", "administration", "Import an encrypted backup file and merge its data into this installation."),
)

PAYROLL_PERMISSION_DEFINITIONS: tuple[PermissionDefinition, ...] = tuple(
    PermissionDefinition(
        code=code,
        name=name,
        module_code="payroll",
        description=description,
    )
    for code, name, description in ALL_PAYROLL_PERMISSIONS
)

ALL_SYSTEM_PERMISSIONS: tuple[PermissionDefinition, ...] = (
    COMPANY_PERMISSION_DEFINITIONS
    + CHART_PERMISSION_DEFINITIONS
    + FISCAL_PERMISSION_DEFINITIONS
    + JOURNAL_PERMISSION_DEFINITIONS
    + REFERENCE_PERMISSION_DEFINITIONS
    + CUSTOMER_PERMISSION_DEFINITIONS
    + SUPPLIER_PERMISSION_DEFINITIONS
    + SALES_PERMISSION_DEFINITIONS
    + PURCHASE_PERMISSION_DEFINITIONS
    + TREASURY_PERMISSION_DEFINITIONS
    + INVENTORY_PERMISSION_DEFINITIONS
    + ASSET_PERMISSION_DEFINITIONS
    + PAYROLL_PERMISSION_DEFINITIONS
    + CONTRACT_PERMISSION_DEFINITIONS
    + JOB_COSTING_PERMISSION_DEFINITIONS
    + BUDGET_PERMISSION_DEFINITIONS
    + REPORTING_PERMISSION_DEFINITIONS
    + MANAGEMENT_PERMISSION_DEFINITIONS
    + AUDIT_PERMISSION_DEFINITIONS
    + ADMINISTRATION_PERMISSION_DEFINITIONS
)

ALL_SYSTEM_PERMISSION_CODES: tuple[str, ...] = tuple(permission.code for permission in ALL_SYSTEM_PERMISSIONS)
SYSTEM_PERMISSION_BY_CODE: dict[str, PermissionDefinition] = {
    permission.code: permission for permission in ALL_SYSTEM_PERMISSIONS
}
NON_PAYROLL_PERMISSION_DEFINITIONS: tuple[PermissionDefinition, ...] = tuple(
    permission for permission in ALL_SYSTEM_PERMISSIONS if permission.module_code != "payroll"
)


def _role(code: str, name: str, description: str, permission_codes: tuple[str, ...]) -> RoleDefinition:
    return RoleDefinition(
        code=code,
        name=name,
        description=description,
        permission_codes=permission_codes,
    )


BASELINE_SYSTEM_ROLES: tuple[RoleDefinition, ...] = (
    _role(
        "company_admin",
        "Company Administrator",
        "Full company administration across configuration, transactions, reporting, security, and audit.",
        ALL_SYSTEM_PERMISSION_CODES,
    ),
    _role(
        "finance_manager",
        "Finance Manager",
        "Cross-module finance oversight covering configuration, posting control, treasury, operational subledgers, and financial reporting.",
        _merge_permission_codes(
            (
                "companies.view",
                "companies.select_active",
                "companies.preferences.manage",
                "companies.fiscal_defaults.manage",
                "companies.project_preferences.manage",
            ),
            _permission_codes_with_prefix(
                "chart.",
                "fiscal.",
                "journals.",
                "reference.",
                "customers.",
                "suppliers.",
                "sales.",
                "purchases.",
                "treasury.",
                "inventory.",
                "assets.",
                "reports.",
                "management.",
            ),
            ("audit.view", "audit.export", "audit.filter"),
        ),
    ),
    _role(
        "general_accountant",
        "General Accountant",
        "Core accounting operator responsible for chart, fiscal periods, journals, reference data, operational posting, and financial reports.",
        _merge_permission_codes(
            ("companies.view", "companies.select_active"),
            _permission_codes_with_prefix(
                "chart.",
                "fiscal.",
                "journals.",
                "reference.",
                "customers.",
                "suppliers.",
                "sales.",
                "purchases.",
                "reports.",
            ),
            (
                "treasury.financial_accounts.view",
                "treasury.transactions.view",
                "treasury.transfers.view",
                "treasury.statement_lines.view",
                "treasury.reconciliation.view",
            ),
        ),
    ),
    _role(
        "ar_officer",
        "Accounts Receivable Officer",
        "Receivables operator responsible for customers, sales invoices, receipts, allocations, and related reporting.",
        _merge_permission_codes(
            ("companies.view", "companies.select_active"),
            _permission_codes_with_prefix("customers.", "sales."),
            (
                "reports.trial_balance.view",
                "reports.general_ledger.view",
                "reports.general_ledger.export",
                "reports.general_ledger.print",
                "reports.ar_aging.view",
                "reports.ar_aging.export",
                "reports.ar_aging.print",
                "reports.customer_statements.view",
                "reports.customer_statements.export",
                "reports.customer_statements.print",
            ),
        ),
    ),
    _role(
        "ap_officer",
        "Accounts Payable Officer",
        "Payables operator responsible for suppliers, purchase bills, supplier payments, allocations, and related reporting.",
        _merge_permission_codes(
            ("companies.view", "companies.select_active"),
            _permission_codes_with_prefix("suppliers.", "purchases."),
            (
                "reports.trial_balance.view",
                "reports.general_ledger.view",
                "reports.general_ledger.export",
                "reports.general_ledger.print",
                "reports.ap_aging.view",
                "reports.ap_aging.export",
                "reports.ap_aging.print",
                "reports.supplier_statements.view",
                "reports.supplier_statements.export",
                "reports.supplier_statements.print",
            ),
        ),
    ),
    _role(
        "treasury_officer",
        "Treasury Officer",
        "Treasury operator responsible for financial accounts, cash and bank transactions, statement imports, and reconciliation.",
        _merge_permission_codes(
            ("companies.view", "companies.select_active"),
            _permission_codes_with_prefix("treasury."),
            (
                "reports.trial_balance.view",
                "reports.general_ledger.view",
                "reports.general_ledger.export",
                "reports.general_ledger.print",
                "reports.treasury_reports.view",
                "reports.treasury_reports.export",
                "reports.treasury_reports.print",
            ),
        ),
    ),
    _role(
        "auditor_read_only",
        "Auditor Read Only",
        "Read-only access to operational records, reports, and audit data without mutation rights.",
        _merge_permission_codes(
            _permission_codes_with_suffix(".view", ".export", ".print", ".preview"),
            ("audit.filter", "audit.read_sensitive", "companies.select_active"),
        ),
    ),
)

BASELINE_SYSTEM_ROLE_CODES: tuple[str, ...] = tuple(role.code for role in BASELINE_SYSTEM_ROLES)
