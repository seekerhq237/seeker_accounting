"""Search providers for the command palette.

Each provider implements a ``search(query) -> list[PaletteResult]`` method.

Providers
---------
* **NavigationProvider** — static sidebar pages + keyword aliases.
* **ActionsProvider** — create-entity and global action commands.
* **EntityProvider** — live DB search across all major entity types.
* **ReportsProvider** — all available report types.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.app.security.permission_map import can_access_navigation
from seeker_accounting.app.shell.command_palette import PaletteResult
from seeker_accounting.app.shell.shell_models import NAVIGATION_BY_ID, NAVIGATION_SECTIONS
from seeker_accounting.modules.payroll.payroll_permissions import (
    PAYROLL_EMPLOYEE_MANAGE,
    PAYROLL_RUN_CREATE,
)
from seeker_accounting.shared.utils.fuzzy_match import fuzzy_score

if TYPE_CHECKING:
    from seeker_accounting.app.context.active_company_context import ActiveCompanyContext
    from seeker_accounting.app.dependency.service_registry import ServiceRegistry
    from seeker_accounting.app.navigation.navigation_service import NavigationService
    from seeker_accounting.modules.administration.services.permission_service import PermissionService

logger = logging.getLogger(__name__)

_MAX_PER_CATEGORY = 5
_NAV_CTX_PALETTE_ACTION = "command_palette_action"
_PALETTE_ACTION_OPEN_CREATE_DIALOG = "open_create_dialog"


# ── helpers ─────────────────────────────────────────────────────────────────

def _best_score(query: str, candidates: list[str]) -> float:
    """Return the highest fuzzy score across *candidates*, or 0."""
    if not query:
        return 0.1  # low default so everything shows with no query
    best = 0.0
    for c in candidates:
        s = fuzzy_score(query, c)
        if s is not None and s > best:
            best = s
    return best


# ═══════════════════════════════════════════════════════════════════════════
# 1. Navigation Provider – sidebar pages
# ═══════════════════════════════════════════════════════════════════════════

# Keyword aliases that let users type abbreviations / synonyms.
_NAV_ALIASES: dict[str, list[str]] = {
    nav_ids.CHART_OF_ACCOUNTS: ["CoA", "GL accounts", "ledger accounts", "account list"],
    nav_ids.JOURNALS: ["GL", "general ledger", "journal entries", "JE"],
    nav_ids.FISCAL_PERIODS: ["periods", "closing", "year end"],
    nav_ids.CUSTOMER_QUOTES: ["quotes", "estimates", "CQ", "quotations", "customer estimates"],
    nav_ids.SALES_INVOICES: ["invoices", "SI", "AR invoices", "sales"],
    nav_ids.CUSTOMER_RECEIPTS: ["AR", "receipts", "customer payments", "collections"],
    nav_ids.PURCHASE_ORDERS: ["PO", "purchase orders", "procurement", "orders"],
    nav_ids.PURCHASE_BILLS: ["bills", "AP invoices", "purchases", "vendor bills"],
    nav_ids.SUPPLIER_PAYMENTS: ["AP", "vendor payments", "disbursements"],
    nav_ids.FINANCIAL_ACCOUNTS: ["bank accounts", "cash accounts", "treasury accounts"],
    nav_ids.TREASURY_TRANSACTIONS: ["cash transactions", "bank transactions"],
    nav_ids.TREASURY_TRANSFERS: ["bank transfers", "inter-account"],
    nav_ids.STATEMENT_LINES: ["bank statements", "statement import"],
    nav_ids.BANK_RECONCILIATION: ["reconcile", "bank rec"],
    nav_ids.CUSTOMERS: ["clients", "debtors"],
    nav_ids.SUPPLIERS: ["vendors", "creditors"],
    nav_ids.ITEMS: ["products", "SKU", "stock items", "goods"],
    nav_ids.INVENTORY_DOCUMENTS: ["stock movements", "goods receipt", "goods issue"],
    nav_ids.STOCK_POSITION: ["stock on hand", "SOH", "inventory levels"],
    nav_ids.ASSETS: ["fixed assets", "asset register", "FA"],
    nav_ids.DEPRECIATION_RUNS: ["depreciation", "amortisation", "amortization"],
    nav_ids.ASSET_CATEGORIES: ["asset types", "FA categories"],
    nav_ids.PAYROLL_SETUP: ["employees", "payroll config", "departments", "positions"],
    nav_ids.PAYROLL_CALCULATION: ["payroll runs", "salary calculation", "pay run"],
    nav_ids.PAYROLL_ACCOUNTING: ["payroll posting", "payroll GL", "salary posting"],
    nav_ids.PAYROLL_OPERATIONS: ["payslips", "statutory", "payroll audit"],
    nav_ids.PAYMENT_TERMS: ["credit terms", "due terms"],
    nav_ids.TAX_CODES: ["VAT", "tax rates", "tax setup"],
    nav_ids.DOCUMENT_SEQUENCES: ["numbering", "auto-number", "sequence"],
    nav_ids.ACCOUNT_ROLE_MAPPINGS: ["control accounts", "role mapping"],
    nav_ids.REPORTS: ["reporting", "financial reports"],
    nav_ids.PROJECTS: ["project list", "project register"],
    nav_ids.CONTRACTS: ["contract list", "contract register"],
    nav_ids.DASHBOARD: ["home", "overview", "main"],
    nav_ids.ORGANISATION_SETTINGS: ["company settings", "org settings", "company profile"],
    nav_ids.ADMINISTRATION: ["admin", "users", "access control", "permissions"],
    nav_ids.ROLES: ["roles", "role management", "permissions", "RBAC"],
    nav_ids.UNITS_OF_MEASURE: ["UoM", "units"],
    nav_ids.ITEM_CATEGORIES: ["product categories", "item groups"],
    nav_ids.INVENTORY_LOCATIONS: ["warehouses", "bins", "storage"],
    nav_ids.PROJECT_VARIANCE_ANALYSIS: ["variance", "budget vs actual", "cost variance"],
    nav_ids.CONTRACT_SUMMARY: ["contract overview", "contract financials"],
    nav_ids.AUDIT_LOG: ["audit log", "audit trail", "activity log", "user activity"],
}

_ENTITY_PERMISSION_BY_NAV_ID: dict[str, str] = {
    nav_ids.CUSTOMERS: "customers.view",
    nav_ids.SUPPLIERS: "suppliers.view",
    nav_ids.CHART_OF_ACCOUNTS: "chart.accounts.view",
    nav_ids.ITEMS: "inventory.items.view",
    nav_ids.SALES_INVOICES: "sales.invoices.view",
    nav_ids.PURCHASE_BILLS: "purchases.bills.view",
    nav_ids.PAYROLL_SETUP: PAYROLL_EMPLOYEE_MANAGE,
    nav_ids.ASSETS: "assets.master.view",
    nav_ids.FINANCIAL_ACCOUNTS: "treasury.financial_accounts.view",
    nav_ids.PROJECTS: "projects.view",
    nav_ids.CONTRACTS: "contracts.view",
    nav_ids.JOURNALS: "journals.view",
}


class NavigationProvider:
    """Search across all sidebar navigation items with fuzzy matching."""

    def __init__(
        self,
        navigation_service: NavigationService,
        permission_service: PermissionService,
    ) -> None:
        self._nav = navigation_service
        self._permission_service = permission_service
        self._items = self._build_items()

    def _build_items(self) -> list[dict[str, Any]]:
        items = []
        for section in NAVIGATION_SECTIONS:
            for nav_item in section.items:
                aliases = _NAV_ALIASES.get(nav_item.nav_id, [])
                search_texts = [
                    nav_item.label,
                    nav_item.description,
                    nav_item.section_label,
                    nav_item.nav_id.replace("_", " "),
                ] + aliases
                items.append({
                    "nav_id": nav_item.nav_id,
                    "label": nav_item.label,
                    "section": nav_item.section_label,
                    "description": nav_item.description,
                    "search_texts": search_texts,
                })
        return items

    def search(self, query: str) -> list[PaletteResult]:
        results: list[PaletteResult] = []
        for item in self._items:
            score = _best_score(query, item["search_texts"])
            if score <= 0:
                continue
            nav_id = item["nav_id"]
            if not can_access_navigation(self._permission_service, nav_id):
                continue
            results.append(PaletteResult(
                category="Pages",
                title=item["label"],
                subtitle=f'{item["section"]} · {item["description"]}',
                icon_hint="navigation",
                score=score,
                action=lambda nid=nav_id: self._nav.navigate(nid),
            ))
        results.sort(key=lambda r: r.score, reverse=True)
        if not query:
            return results  # Show all pages when browsing with empty query.
        return results[:_MAX_PER_CATEGORY * 2]  # navigation gets double quota


# ═══════════════════════════════════════════════════════════════════════════
# 2. Actions Provider – create commands and global actions
# ═══════════════════════════════════════════════════════════════════════════

class ActionsProvider:
    """Provides action commands (create entity, toggle theme, switch company, etc.)."""

    def __init__(
        self,
        navigation_service: NavigationService,
        service_registry: ServiceRegistry,
    ) -> None:
        self._nav = navigation_service
        self._sr = service_registry
        self._actions = self._build_actions()

    def _build_actions(self) -> list[dict[str, Any]]:
        n = self._nav
        sr = self._sr
        actions: list[dict[str, Any]] = []

        def _add(
            label: str,
            subtitle: str,
            nav_id: str,
            keywords: list[str] | None = None,
            ctx: dict | None = None,
            required_permission: str | None = None,
        ) -> None:
            kw = keywords or []
            search_texts = [label] + kw

            def _execute_action(nid: str = nav_id, c: dict | None = ctx) -> None:
                context_payload: dict[str, Any] = dict(c or {})
                context_payload.setdefault(
                    _NAV_CTX_PALETTE_ACTION,
                    _PALETTE_ACTION_OPEN_CREATE_DIALOG,
                )
                n.navigate(nid, context=context_payload)

            actions.append({
                "label": label,
                "subtitle": subtitle,
                "search_texts": search_texts,
                "action": _execute_action,
                "needs_company": True,
                "required_permission": required_permission,
            })

        def _add_global(label: str, subtitle: str, action, keywords: list[str] | None = None) -> None:
            kw = keywords or []
            search_texts = [label] + kw
            actions.append({
                "label": label,
                "subtitle": subtitle,
                "search_texts": search_texts,
                "action": action,
                "needs_company": False,
            })

        # ── Global actions ──
        _add_global("Toggle Theme", "Switch between light and dark theme",
                     sr.theme_manager.toggle_theme, ["dark mode", "light mode", "theme"])

        # ── Company-scoped creation actions ──
        _add("Create Customer", "Add a new customer record", nav_ids.CUSTOMERS,
             ["new customer", "add customer", "add client"], required_permission="customers.create")
        _add("Create Supplier", "Add a new supplier record", nav_ids.SUPPLIERS,
             ["new supplier", "add supplier", "add vendor"], required_permission="suppliers.create")
        _add("Create Customer Quote", "Draft a new customer quote or estimate", nav_ids.CUSTOMER_QUOTES,
             ["new quote", "add quote", "new estimate", "create estimate"], required_permission="sales.quotes.create")
        _add("Create Sales Invoice", "Draft a new sales invoice", nav_ids.SALES_INVOICES,
             ["new invoice", "add invoice", "issue invoice"], required_permission="sales.invoices.create")
        _add("Create Purchase Order", "Draft a new purchase order", nav_ids.PURCHASE_ORDERS,
             ["new PO", "add order", "new order", "purchase requisition"], required_permission="purchases.orders.create")
        _add("Create Purchase Bill", "Draft a new purchase bill", nav_ids.PURCHASE_BILLS,
             ["new bill", "add bill", "vendor bill"], required_permission="purchases.bills.create")
        _add("Create Customer Receipt", "Record a customer payment", nav_ids.CUSTOMER_RECEIPTS,
             ["new receipt", "receive payment", "AR receipt"], required_permission="sales.receipts.create")
        _add("Create Supplier Payment", "Record a payment to supplier", nav_ids.SUPPLIER_PAYMENTS,
             ["new payment", "pay supplier", "AP payment", "disbursement"], required_permission="purchases.payments.create")
        _add("Create Journal Entry", "Draft a new manual journal entry", nav_ids.JOURNALS,
             ["new journal", "add JE", "manual journal", "journal voucher"], required_permission="journals.create")
        _add("Create Item", "Add a new inventory item", nav_ids.ITEMS,
             ["new item", "add product", "new product", "add SKU"], required_permission="inventory.items.create")
        _add("Create Inventory Document", "New stock receipt, issue, or adjustment", nav_ids.INVENTORY_DOCUMENTS,
             ["new stock movement", "goods receipt", "goods issue", "stock adjustment"], required_permission="inventory.documents.create")
        _add("Create Financial Account", "Add a new bank or cash account", nav_ids.FINANCIAL_ACCOUNTS,
             ["new bank account", "add cash account", "new treasury account"], required_permission="treasury.financial_accounts.create")
        _add("Create Treasury Transaction", "Record a cash/bank transaction", nav_ids.TREASURY_TRANSACTIONS,
             ["new transaction", "cash receipt", "cash payment"], required_permission="treasury.transactions.create")
        _add("Create Transfer", "Create an inter-account transfer", nav_ids.TREASURY_TRANSFERS,
             ["new transfer", "bank transfer", "move funds"], required_permission="treasury.transfers.create")
        _add("Create Asset", "Register a new fixed asset", nav_ids.ASSETS,
             ["new asset", "add asset", "new fixed asset", "capitalise"], required_permission="assets.master.create")
        _add("Create Employee", "Add a new employee record", nav_ids.PAYROLL_SETUP,
             ["new employee", "add employee", "hire"], required_permission=PAYROLL_EMPLOYEE_MANAGE)
        _add("Create Payroll Run", "Start a new payroll calculation", nav_ids.PAYROLL_CALCULATION,
             ["new payroll", "run payroll", "calculate salary"], required_permission=PAYROLL_RUN_CREATE)
        _add("Create Contract", "Add a new contract", nav_ids.CONTRACTS,
             ["new contract", "add contract"], required_permission="contracts.create")
        _add("Create Project", "Add a new project", nav_ids.PROJECTS,
             ["new project", "add project"], required_permission="projects.create")
        _add("Create Account", "Add a new chart of accounts entry", nav_ids.CHART_OF_ACCOUNTS,
             ["new account", "add GL account", "new ledger account"], required_permission="chart.accounts.create")
        _add("Create Payment Term", "Add a new payment term", nav_ids.PAYMENT_TERMS,
             ["new payment term", "add credit term"], required_permission="reference.payment_terms.create")
        _add("Create Tax Code", "Add a new tax code", nav_ids.TAX_CODES,
             ["new tax code", "add VAT rate", "new tax rate"], required_permission="reference.tax_codes.create")

        return actions

    def search(self, query: str) -> list[PaletteResult]:
        company_id = self._sr.active_company_context.company_id
        results: list[PaletteResult] = []
        for action in self._actions:
            if action["needs_company"] and not company_id:
                continue
            required_permission = action.get("required_permission")
            if required_permission and not self._sr.permission_service.has_permission(required_permission):
                continue
            score = _best_score(query, action["search_texts"])
            if score <= 0:
                continue
            # Boost action scores slightly below navigation so pages rank first
            # when query is ambiguous, but actions still appear when explicit.
            results.append(PaletteResult(
                category="Actions",
                title=action["label"],
                subtitle=action["subtitle"],
                icon_hint="action",
                score=score * 0.9,
                action=action["action"],
            ))
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:_MAX_PER_CATEGORY]


# ═══════════════════════════════════════════════════════════════════════════
# 3. Entity Provider – live DB search across all major entity types
# ═══════════════════════════════════════════════════════════════════════════

class _EntityDef:
    """Descriptor for a single searchable entity type."""

    __slots__ = ("category", "nav_id", "fetch", "display_fn", "search_fields_fn")

    def __init__(
        self,
        category: str,
        nav_id: str,
        fetch,
        display_fn,
        search_fields_fn,
    ) -> None:
        self.category = category
        self.nav_id = nav_id
        self.fetch = fetch  # callable(company_id) -> list[dto]
        self.display_fn = display_fn  # callable(dto) -> (title, subtitle)
        self.search_fields_fn = search_fields_fn  # callable(dto) -> list[str]


class EntityProvider:
    """Live DB search across all major entity types.

    Each keystroke triggers service calls (debounced upstream).  Results are
    fuzzy-scored client-side.  Only active-company entities are searched.
    """

    def __init__(self, service_registry: ServiceRegistry) -> None:
        self._sr = service_registry
        self._acc = service_registry.active_company_context
        self._nav = service_registry.navigation_service
        self._defs = self._build_definitions()

    def _build_contextual_actions(
        self,
        *,
        entity_category: str,
        entity_title: str,
        query: str,
    ) -> list[PaletteResult]:
        sr = self._sr
        contextual_specs: list[dict[str, str]] = []

        if entity_category == "Customers":
            contextual_specs = [
                {
                    "title": f"Create Sales Invoice for {entity_title}",
                    "subtitle": "Open Sales Invoices and launch create dialog",
                    "nav_id": nav_ids.SALES_INVOICES,
                    "permission": "sales.invoices.create",
                    "keywords": f"invoice customer {entity_title}",
                },
                {
                    "title": f"Record Customer Receipt for {entity_title}",
                    "subtitle": "Open Customer Receipts and launch create dialog",
                    "nav_id": nav_ids.CUSTOMER_RECEIPTS,
                    "permission": "sales.receipts.create",
                    "keywords": f"receipt payment customer {entity_title}",
                },
            ]
        elif entity_category == "Suppliers":
            contextual_specs = [
                {
                    "title": f"Create Purchase Order for {entity_title}",
                    "subtitle": "Open Purchase Orders and launch create dialog",
                    "nav_id": nav_ids.PURCHASE_ORDERS,
                    "permission": "purchases.orders.create",
                    "keywords": f"PO order supplier {entity_title}",
                },
                {
                    "title": f"Create Purchase Bill for {entity_title}",
                    "subtitle": "Open Purchase Bills and launch create dialog",
                    "nav_id": nav_ids.PURCHASE_BILLS,
                    "permission": "purchases.bills.create",
                    "keywords": f"bill supplier {entity_title}",
                },
                {
                    "title": f"Record Supplier Payment for {entity_title}",
                    "subtitle": "Open Supplier Payments and launch create dialog",
                    "nav_id": nav_ids.SUPPLIER_PAYMENTS,
                    "permission": "purchases.payments.create",
                    "keywords": f"payment supplier {entity_title}",
                },
            ]
        elif entity_category == "Items":
            contextual_specs = [
                {
                    "title": f"Create Inventory Document for {entity_title}",
                    "subtitle": "Open Inventory Documents and launch create dialog",
                    "nav_id": nav_ids.INVENTORY_DOCUMENTS,
                    "permission": "inventory.documents.create",
                    "keywords": f"stock issue stock receipt item {entity_title}",
                },
            ]
        elif entity_category == "Accounts":
            contextual_specs = [
                {
                    "title": f"Create Journal Entry for {entity_title}",
                    "subtitle": "Open Journals and launch create dialog",
                    "nav_id": nav_ids.JOURNALS,
                    "permission": "journals.create",
                    "keywords": f"journal entry account {entity_title}",
                },
            ]

        results: list[PaletteResult] = []
        for spec in contextual_specs:
            permission_code = spec["permission"]
            if not sr.permission_service.has_permission(permission_code):
                continue
            score = _best_score(query, [spec["title"], spec["keywords"], entity_title])
            if score <= 0:
                continue
            nav_id = spec["nav_id"]
            results.append(PaletteResult(
                category="Quick Actions",
                title=spec["title"],
                subtitle=spec["subtitle"],
                icon_hint="action",
                score=score * 0.72,
                action=lambda nid=nav_id, title=entity_title: self._nav.navigate(
                    nid,
                    context={
                        _NAV_CTX_PALETTE_ACTION: _PALETTE_ACTION_OPEN_CREATE_DIALOG,
                        "source_entity_title": title,
                    },
                ),
            ))
        return results

    def _build_definitions(self) -> list[_EntityDef]:
        sr = self._sr
        return [
            # ── Customers ──
            _EntityDef(
                category="Customers",
                nav_id=nav_ids.CUSTOMERS,
                fetch=lambda cid: sr.customer_service.list_customers(cid),
                display_fn=lambda d: (d.display_name, f"Customer · {d.customer_code}"),
                search_fields_fn=lambda d: [d.display_name, d.customer_code],
            ),
            # ── Suppliers ──
            _EntityDef(
                category="Suppliers",
                nav_id=nav_ids.SUPPLIERS,
                fetch=lambda cid: sr.supplier_service.list_suppliers(cid),
                display_fn=lambda d: (d.display_name, f"Supplier · {d.supplier_code}"),
                search_fields_fn=lambda d: [d.display_name, d.supplier_code],
            ),
            # ── Accounts ──
            _EntityDef(
                category="Accounts",
                nav_id=nav_ids.CHART_OF_ACCOUNTS,
                fetch=lambda cid: sr.chart_of_accounts_service.list_accounts(cid),
                display_fn=lambda d: (f"{d.account_code} – {d.account_name}", f"{d.account_class_name} · {d.account_type_name}"),
                search_fields_fn=lambda d: [d.account_name, d.account_code, d.account_class_name],
            ),
            # ── Items ──
            _EntityDef(
                category="Items",
                nav_id=nav_ids.ITEMS,
                fetch=lambda cid: sr.item_service.list_items(cid),
                display_fn=lambda d: (d.item_name, f"Item · {d.item_code} · {d.item_type_code}"),
                search_fields_fn=lambda d: [d.item_name, d.item_code],
            ),
            # ── Sales Invoices ──
            _EntityDef(
                category="Sales Invoices",
                nav_id=nav_ids.SALES_INVOICES,
                fetch=lambda cid: sr.sales_invoice_service.list_sales_invoices(cid),
                display_fn=lambda d: (d.invoice_number, f"{d.customer_name} · {d.status_code} · {d.total_amount:,.2f}"),
                search_fields_fn=lambda d: [d.invoice_number, d.customer_name, d.customer_code],
            ),
            # ── Purchase Orders ──
            _EntityDef(
                category="Purchase Orders",
                nav_id=nav_ids.PURCHASE_ORDERS,
                fetch=lambda cid: sr.purchase_order_service.list_orders(cid),
                display_fn=lambda d: (d.order_number, f"{d.supplier_name} · {d.status_code} · {d.total_amount:,.2f}"),
                search_fields_fn=lambda d: [d.order_number, d.supplier_name, d.supplier_code],
            ),
            # ── Purchase Bills ──
            _EntityDef(
                category="Purchase Bills",
                nav_id=nav_ids.PURCHASE_BILLS,
                fetch=lambda cid: sr.purchase_bill_service.list_purchase_bills(cid),
                display_fn=lambda d: (d.bill_number, f"{d.supplier_name} · {d.status_code} · {d.total_amount:,.2f}"),
                search_fields_fn=lambda d: [d.bill_number, d.supplier_name, d.supplier_code],
            ),
            # ── Employees ──
            _EntityDef(
                category="Employees",
                nav_id=nav_ids.PAYROLL_SETUP,
                fetch=lambda cid: sr.employee_service.list_employees(cid),
                display_fn=lambda d: (d.display_name, f"Employee · {d.employee_number}" + (f" · {d.department_name}" if d.department_name else "")),
                search_fields_fn=lambda d: [d.display_name, d.employee_number, d.first_name, d.last_name],
            ),
            # ── Assets ──
            _EntityDef(
                category="Assets",
                nav_id=nav_ids.ASSETS,
                fetch=lambda cid: sr.asset_service.list_assets(cid),
                display_fn=lambda d: (d.asset_name, f"Asset · {d.asset_number} · {d.asset_category_name}"),
                search_fields_fn=lambda d: [d.asset_name, d.asset_number, d.asset_category_name],
            ),
            # ── Financial Accounts ──
            _EntityDef(
                category="Financial Accounts",
                nav_id=nav_ids.FINANCIAL_ACCOUNTS,
                fetch=lambda cid: sr.financial_account_service.list_financial_accounts(cid),
                display_fn=lambda d: (d.name, f"{d.financial_account_type_code} · {d.account_code} · {d.currency_code}"),
                search_fields_fn=lambda d: [d.name, d.account_code],
            ),
            # ── Projects ──
            _EntityDef(
                category="Projects",
                nav_id=nav_ids.PROJECTS,
                fetch=lambda cid: sr.project_service.list_projects(cid),
                display_fn=lambda d: (d.project_name, f"Project · {d.project_code} · {d.status_code}"),
                search_fields_fn=lambda d: [d.project_name, d.project_code],
            ),
            # ── Contracts ──
            _EntityDef(
                category="Contracts",
                nav_id=nav_ids.CONTRACTS,
                fetch=lambda cid: sr.contract_service.list_contracts(cid),
                display_fn=lambda d: (d.contract_title, f"Contract · {d.contract_number} · {d.customer_display_name}"),
                search_fields_fn=lambda d: [d.contract_title, d.contract_number, d.customer_display_name],
            ),
            # ── Journal Entries ──
            _EntityDef(
                category="Journal Entries",
                nav_id=nav_ids.JOURNALS,
                fetch=lambda cid: sr.journal_service.list_journal_entries(cid),
                display_fn=lambda d: (
                    d.entry_number or "(Draft)",
                    f"{d.journal_type_code} · {d.entry_date} · {d.status_code}"
                    + (f" · {d.description}" if d.description else ""),
                ),
                search_fields_fn=lambda d: [
                    d.entry_number or "",
                    d.description or "",
                    d.reference_text or "",
                    d.journal_type_code,
                ],
            ),
        ]

    def search(self, query: str) -> list[PaletteResult]:
        company_id = self._acc.company_id
        if not company_id or not query or len(query) < 2:
            return []

        all_results: list[PaletteResult] = []

        for edef in self._defs:
            if not can_access_navigation(self._sr.permission_service, edef.nav_id):
                continue
            try:
                entities = edef.fetch(company_id)
            except Exception:
                logger.debug("Entity search failed for %s", edef.category, exc_info=True)
                continue

            category_results: list[PaletteResult] = []
            for entity in entities:
                try:
                    fields = edef.search_fields_fn(entity)
                except Exception:
                    continue
                score = _best_score(query, fields)
                if score <= 0:
                    continue

                title, subtitle = edef.display_fn(entity)
                nav_id = edef.nav_id
                category_results.append(PaletteResult(
                    category=edef.category,
                    title=title,
                    subtitle=subtitle,
                    icon_hint="entity",
                    # Entity scores slightly below actions so they don't dominate
                    # when the query also matches a page/action.
                    score=score * 0.75,
                    action=lambda nid=nav_id: self._nav.navigate(nid),
                ))
                all_results.extend(
                    self._build_contextual_actions(
                        entity_category=edef.category,
                        entity_title=title,
                        query=query,
                    )
                )

            category_results.sort(key=lambda r: r.score, reverse=True)
            all_results.extend(category_results[:_MAX_PER_CATEGORY])

        return all_results


# ═══════════════════════════════════════════════════════════════════════════
# 4. Reports Provider – all report types
# ═══════════════════════════════════════════════════════════════════════════

_REPORT_DEFS: list[dict[str, Any]] = [
    {"label": "Trial Balance", "keywords": ["TB"],
     "subtitle": "Period trial balance report"},
    {"label": "General Ledger", "keywords": ["GL", "ledger detail"],
     "subtitle": "Detailed ledger transactions"},
    {"label": "Balance Sheet (OHADA)", "keywords": ["BS", "bilan", "OHADA balance"],
     "subtitle": "OHADA-format balance sheet"},
    {"label": "Balance Sheet (IAS)", "keywords": ["BS IAS", "IFRS balance"],
     "subtitle": "IAS/IFRS-format balance sheet"},
    {"label": "Income Statement (OHADA)", "keywords": ["PL", "profit loss", "compte de resultat", "OHADA income"],
     "subtitle": "OHADA-format income statement"},
    {"label": "Income Statement (IAS)", "keywords": ["PL IAS", "IFRS income"],
     "subtitle": "IAS/IFRS-format income statement"},
    {"label": "AR Aging Report", "keywords": ["receivables aging", "customer aging", "debtor aging"],
     "subtitle": "Accounts receivable aging analysis"},
    {"label": "AP Aging Report", "keywords": ["payables aging", "supplier aging", "creditor aging"],
     "subtitle": "Accounts payable aging analysis"},
    {"label": "Customer Statement", "keywords": ["debtor statement", "AR statement"],
     "subtitle": "Individual customer account statement"},
    {"label": "Supplier Statement", "keywords": ["creditor statement", "AP statement"],
     "subtitle": "Individual supplier account statement"},
    {"label": "Stock Movement Report", "keywords": ["inventory movement", "stock transactions"],
     "subtitle": "Stock movement detail by item"},
    {"label": "Stock Valuation Report", "keywords": ["inventory valuation", "COGS"],
     "subtitle": "Current stock valuation summary"},
    {"label": "Fixed Asset Register", "keywords": ["asset listing", "FA register"],
     "subtitle": "Complete fixed asset register"},
    {"label": "Depreciation Report", "keywords": ["depreciation schedule", "amortisation report"],
     "subtitle": "Depreciation charges and schedule"},
    {"label": "Payroll Summary Report", "keywords": ["salary summary", "payroll totals"],
     "subtitle": "Payroll run summary by department"},
    {"label": "Treasury Report", "keywords": ["cash flow", "bank summary", "treasury summary"],
     "subtitle": "Treasury position and flows"},
    {"label": "Financial Analysis", "keywords": ["ratio analysis", "financial ratios", "KPI"],
     "subtitle": "Financial ratio and trend analysis"},
    {"label": "Working Capital Analysis", "keywords": ["liquidity", "current ratio", "working capital"],
     "subtitle": "Working capital position and trends"},
    {"label": "Project Variance Analysis", "keywords": ["budget variance", "cost variance", "EAC"],
     "subtitle": "Budget vs actual by project"},
    {"label": "Contract Summary Report", "keywords": ["contract financials", "contract overview"],
     "subtitle": "Financial summary by contract"},
]


class ReportsProvider:
    """Search across all available reports."""

    def __init__(
        self,
        navigation_service: NavigationService,
        permission_service: PermissionService,
    ) -> None:
        self._nav = navigation_service
        self._permission_service = permission_service
        self._items = self._build_items()

    def _build_items(self) -> list[dict[str, Any]]:
        items = []
        for rdef in _REPORT_DEFS:
            search_texts = [rdef["label"]] + rdef.get("keywords", [])
            items.append({
                "label": rdef["label"],
                "subtitle": rdef["subtitle"],
                "search_texts": search_texts,
            })
        return items

    def search(self, query: str) -> list[PaletteResult]:
        nav = self._nav
        if not can_access_navigation(self._permission_service, nav_ids.REPORTS):
            return []
        results: list[PaletteResult] = []
        for item in self._items:
            score = _best_score(query, item["search_texts"])
            if score <= 0:
                continue
            results.append(PaletteResult(
                category="Reports",
                title=item["label"],
                subtitle=item["subtitle"],
                icon_hint="report",
                score=score * 0.85,
                action=lambda: nav.navigate(nav_ids.REPORTS),
            ))
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:_MAX_PER_CATEGORY]
