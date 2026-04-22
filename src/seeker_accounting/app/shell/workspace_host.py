from __future__ import annotations

from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QStackedWidget, QVBoxLayout, QWidget

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.app.security.permission_map import (
    build_navigation_denied_message,
    can_access_navigation,
)
from seeker_accounting.app.shell.shell_models import PLACEHOLDER_PAGES, PlaceholderPageModel


_NAV_CTX_PALETTE_ACTION = "command_palette_action"
_PALETTE_ACTION_OPEN_CREATE_DIALOG = "open_create_dialog"


class PlaceholderWorkspacePage(QWidget):
    def __init__(self, model: PlaceholderPageModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._model = model

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(24, 12, 24, 22)
        root_layout.setSpacing(16)

        root_layout.addWidget(self._build_focus_surface())
        root_layout.addLayout(self._build_support_surfaces())
        root_layout.addStretch(1)

    def _build_focus_surface(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(8)

        title = QLabel("Overview", card)
        title.setObjectName("InfoCardTitle")
        layout.addWidget(title)

        summary = QLabel(self._model.summary, card)
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)
        return card

    def _build_support_surfaces(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)

        grid.addWidget(self._build_info_surface("Ready Now", self._model.available_now), 0, 0)
        grid.addWidget(self._build_info_surface("Coming Next", self._model.next_slice), 0, 1)
        return grid

    def _build_info_surface(self, title_text: str, lines: tuple[str, ...]) -> QWidget:
        card = QFrame(self)
        card.setObjectName("InfoCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)

        title = QLabel(title_text, card)
        title.setObjectName("InfoCardTitle")
        layout.addWidget(title)

        for line in lines:
            item = QLabel(f"- {line}", card)
            item.setObjectName("InfoCardLine")
            item.setWordWrap(True)
            layout.addWidget(item)

        layout.addStretch(1)
        return card


class AccessDeniedWorkspacePage(QWidget):
    def __init__(self, title_text: str, message: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(24, 12, 24, 22)
        root_layout.setSpacing(16)
        root_layout.addStretch(1)

        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(8)

        title = QLabel(title_text, card)
        title.setObjectName("EmptyStateTitle")
        title.setWordWrap(True)
        layout.addWidget(title)

        summary = QLabel(message, card)
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        root_layout.addWidget(card)
        root_layout.addStretch(1)


class WorkspaceHost(QFrame):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._navigation_service = service_registry.navigation_service
        self._page_indexes: dict[str, int] = {}
        self._page_models: dict[str, PlaceholderPageModel] = {}
        self._materialized_pages: set[str] = set()
        self._last_navigation_context_by_nav_id: dict[str, dict[str, Any]] = {}

        self.setObjectName("WorkspaceFrame")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._stack = QStackedWidget(self)
        layout.addWidget(self._stack)

        # Register lightweight blank placeholders; real pages are created on
        # first navigation.  This keeps the initial widget count low, which
        # makes theme switching (app.setStyleSheet) fast — Qt cost is
        # proportional to the number of live widgets.
        for nav_id, model in PLACEHOLDER_PAGES.items():
            self._page_models[nav_id] = model
            blank = QWidget(self._stack)
            index = self._stack.addWidget(blank)
            self._page_indexes[nav_id] = index

        self._navigation_service.navigation_changed.connect(self._set_current_page)
        self._navigation_service.navigation_context_changed.connect(self._on_navigation_context_changed)
        self._set_current_page(self._navigation_service.current_nav_id)

    def _ensure_page_materialized(self, nav_id: str) -> None:
        """Create the real page widget on first access, replacing the blank placeholder."""
        if nav_id in self._materialized_pages:
            return
        index = self._page_indexes[nav_id]
        old_placeholder = self._stack.widget(index)
        model = self._page_models[nav_id]
        real_page = self._create_page(nav_id, model)
        self._stack.insertWidget(index, real_page)
        self._stack.removeWidget(old_placeholder)
        old_placeholder.deleteLater()
        # insertWidget shifts indexes of widgets after 'index', but removeWidget
        # of the old widget (now at index+1) restores the original mapping, so
        # _page_indexes remains correct.
        self._materialized_pages.add(nav_id)

    def _set_current_page(self, nav_id: str) -> None:
        self._ensure_page_materialized(nav_id)
        index = self._page_indexes[nav_id]
        self._stack.setCurrentIndex(index)
        # Do NOT apply navigation context here. NavigationService always emits
        # navigation_context_changed immediately after navigation_changed, so
        # _on_navigation_context_changed will apply the fresh context. Applying
        # context from _last_navigation_context_by_nav_id here would hand stale
        # context (e.g. an old resume token) to a page that is being re-visited
        # via a plain navigate() call with no token.

    def _on_navigation_context_changed(self, nav_id: str, context: object) -> None:
        normalized_context = context if isinstance(context, dict) else {}
        # Always overwrite with the fresh context emitted by NavigationService.
        # This is the single authoritative write point for per-nav-id context state.
        self._last_navigation_context_by_nav_id[nav_id] = dict(normalized_context)
        if nav_id == self._navigation_service.current_nav_id:
            self._apply_navigation_context(nav_id)

    def _apply_navigation_context(self, nav_id: str) -> None:
        context = self._last_navigation_context_by_nav_id.get(nav_id)
        if context is None:
            context = self._navigation_service.current_navigation_context
            self._last_navigation_context_by_nav_id[nav_id] = dict(context)

        context_to_apply = dict(context)
        palette_action = context_to_apply.pop(_NAV_CTX_PALETTE_ACTION, None)
        self._last_navigation_context_by_nav_id[nav_id] = dict(context_to_apply)

        page = self._stack.currentWidget()
        apply_context = getattr(page, "set_navigation_context", None)
        if callable(apply_context):
            apply_context(dict(context_to_apply))

        if palette_action == _PALETTE_ACTION_OPEN_CREATE_DIALOG:
            open_create_dialog = getattr(page, "_open_create_dialog", None)
            if callable(open_create_dialog):
                QTimer.singleShot(0, open_create_dialog)

    def get_last_navigation_context(self, nav_id: str | None = None) -> dict[str, Any] | None:
        target_nav_id = nav_id or self._navigation_service.current_nav_id
        context = self._last_navigation_context_by_nav_id.get(target_nav_id)
        if context is None:
            return None
        return dict(context)

    def consume_resume_token(self, nav_id: str | None = None) -> str | None:
        target_nav_id = nav_id or self._navigation_service.current_nav_id
        context = self._last_navigation_context_by_nav_id.get(target_nav_id)
        if not context:
            return None
        token = context.pop("resume_token", None)
        if token is None:
            return None
        self._last_navigation_context_by_nav_id[target_nav_id] = context
        return str(token)

    def _create_page(self, nav_id: str, model: PlaceholderPageModel) -> QWidget:
        if not can_access_navigation(self._service_registry.permission_service, nav_id):
            return AccessDeniedWorkspacePage(
                title_text=f"{model.title} is unavailable",
                message=build_navigation_denied_message(
                    self._service_registry.permission_service,
                    nav_id,
                ),
                parent=self._stack,
            )

        page = self._create_feature_page(nav_id, model)

        # Install the floating contextual help button on every feature page.
        from seeker_accounting.shared.ui.help_button import install_help_button
        install_help_button(page, nav_id)

        return page

    def _create_feature_page(self, nav_id: str, model: PlaceholderPageModel) -> QWidget:
        # Lazy imports — each module is loaded only when its page is first visited.
        if nav_id == nav_ids.DASHBOARD:
            from seeker_accounting.modules.dashboard.ui.dashboard_page import DashboardPage
            return DashboardPage(self._service_registry, self._stack)
        if nav_id == nav_ids.ORGANISATION_SETTINGS:
            from seeker_accounting.modules.companies.ui.organisation_settings_page import OrganisationSettingsPage
            return OrganisationSettingsPage(self._service_registry, self._stack)
        if nav_id == nav_ids.CUSTOMERS:
            from seeker_accounting.modules.customers.ui.customers_page import CustomersPage
            return CustomersPage(self._service_registry, self._stack)
        if nav_id == nav_ids.SUPPLIERS:
            from seeker_accounting.modules.suppliers.ui.suppliers_page import SuppliersPage
            return SuppliersPage(self._service_registry, self._stack)
        if nav_id == nav_ids.PAYMENT_TERMS:
            from seeker_accounting.modules.accounting.reference_data.ui.payment_terms_page import PaymentTermsPage
            return PaymentTermsPage(self._service_registry, self._stack)
        if nav_id == nav_ids.TAX_CODES:
            from seeker_accounting.modules.accounting.reference_data.ui.tax_codes_page import TaxCodesPage
            return TaxCodesPage(self._service_registry, self._stack)
        if nav_id == nav_ids.DOCUMENT_SEQUENCES:
            from seeker_accounting.modules.accounting.reference_data.ui.document_sequences_page import DocumentSequencesPage
            return DocumentSequencesPage(self._service_registry, self._stack)
        if nav_id == nav_ids.CHART_OF_ACCOUNTS:
            from seeker_accounting.modules.accounting.chart_of_accounts.ui.chart_of_accounts_page import ChartOfAccountsPage
            return ChartOfAccountsPage(self._service_registry, self._stack)
        if nav_id == nav_ids.ACCOUNT_ROLE_MAPPINGS:
            from seeker_accounting.modules.accounting.reference_data.ui.account_role_mappings_page import AccountRoleMappingsPage
            return AccountRoleMappingsPage(self._service_registry, self._stack)
        if nav_id == nav_ids.FISCAL_PERIODS:
            from seeker_accounting.modules.accounting.fiscal_periods.ui.fiscal_periods_page import FiscalPeriodsPage
            return FiscalPeriodsPage(self._service_registry, self._stack)
        if nav_id == nav_ids.JOURNALS:
            from seeker_accounting.modules.accounting.journals.ui.journals_page import JournalsPage
            return JournalsPage(self._service_registry, self._stack)
        if nav_id == nav_ids.CUSTOMER_QUOTES:
            from seeker_accounting.modules.sales.ui.customer_quotes_page import CustomerQuotesPage
            return CustomerQuotesPage(self._service_registry, self._stack)
        if nav_id == nav_ids.SALES_ORDERS:
            from seeker_accounting.modules.sales.ui.sales_orders_page import SalesOrdersPage
            return SalesOrdersPage(self._service_registry, self._stack)
        if nav_id == nav_ids.SALES_CREDIT_NOTES:
            from seeker_accounting.modules.sales.ui.sales_credit_notes_page import SalesCreditNotesPage
            return SalesCreditNotesPage(self._service_registry, self._stack)
        if nav_id == nav_ids.SALES_INVOICES:
            from seeker_accounting.modules.sales.ui.sales_invoices_page import SalesInvoicesPage
            return SalesInvoicesPage(self._service_registry, self._stack)
        if nav_id == nav_ids.CUSTOMER_RECEIPTS:
            from seeker_accounting.modules.sales.ui.customer_receipts_page import CustomerReceiptsPage
            return CustomerReceiptsPage(self._service_registry, self._stack)
        if nav_id == nav_ids.PURCHASE_ORDERS:
            from seeker_accounting.modules.purchases.ui.purchase_orders_page import PurchaseOrdersPage
            return PurchaseOrdersPage(self._service_registry, self._stack)
        if nav_id == nav_ids.PURCHASE_CREDIT_NOTES:
            from seeker_accounting.modules.purchases.ui.purchase_credit_notes_page import PurchaseCreditNotesPage
            return PurchaseCreditNotesPage(self._service_registry, self._stack)
        if nav_id == nav_ids.PURCHASE_BILLS:
            from seeker_accounting.modules.purchases.ui.purchase_bills_page import PurchaseBillsPage
            return PurchaseBillsPage(self._service_registry, self._stack)
        if nav_id == nav_ids.SUPPLIER_PAYMENTS:
            from seeker_accounting.modules.purchases.ui.supplier_payments_page import SupplierPaymentsPage
            return SupplierPaymentsPage(self._service_registry, self._stack)
        if nav_id == nav_ids.FINANCIAL_ACCOUNTS:
            from seeker_accounting.modules.treasury.ui.financial_accounts_page import FinancialAccountsPage
            return FinancialAccountsPage(self._service_registry, self._stack)
        if nav_id == nav_ids.TREASURY_TRANSACTIONS:
            from seeker_accounting.modules.treasury.ui.treasury_transactions_page import TreasuryTransactionsPage
            return TreasuryTransactionsPage(self._service_registry, self._stack)
        if nav_id == nav_ids.TREASURY_TRANSFERS:
            from seeker_accounting.modules.treasury.ui.treasury_transfers_page import TreasuryTransfersPage
            return TreasuryTransfersPage(self._service_registry, self._stack)
        if nav_id == nav_ids.STATEMENT_LINES:
            from seeker_accounting.modules.treasury.ui.statement_lines_page import StatementLinesPage
            return StatementLinesPage(self._service_registry, self._stack)
        if nav_id == nav_ids.BANK_RECONCILIATION:
            from seeker_accounting.modules.treasury.ui.bank_reconciliation_page import BankReconciliationPage
            return BankReconciliationPage(self._service_registry, self._stack)
        if nav_id == nav_ids.UOM_CATEGORIES:
            from seeker_accounting.modules.inventory.ui.uom_categories_page import UomCategoriesPage
            return UomCategoriesPage(self._service_registry, self._stack)
        if nav_id == nav_ids.UNITS_OF_MEASURE:
            from seeker_accounting.modules.inventory.ui.units_of_measure_page import UnitsOfMeasurePage
            return UnitsOfMeasurePage(self._service_registry, self._stack)
        if nav_id == nav_ids.ITEM_CATEGORIES:
            from seeker_accounting.modules.inventory.ui.item_categories_page import ItemCategoriesPage
            return ItemCategoriesPage(self._service_registry, self._stack)
        if nav_id == nav_ids.INVENTORY_LOCATIONS:
            from seeker_accounting.modules.inventory.ui.inventory_locations_page import InventoryLocationsPage
            return InventoryLocationsPage(self._service_registry, self._stack)
        if nav_id == nav_ids.ITEMS:
            from seeker_accounting.modules.inventory.ui.items_page import ItemsPage
            return ItemsPage(self._service_registry, self._stack)
        if nav_id == nav_ids.INVENTORY_DOCUMENTS:
            from seeker_accounting.modules.inventory.ui.inventory_documents_page import InventoryDocumentsPage
            return InventoryDocumentsPage(self._service_registry, self._stack)
        if nav_id == nav_ids.STOCK_POSITION:
            from seeker_accounting.modules.inventory.ui.inventory_stock_view import InventoryStockView
            return InventoryStockView(self._service_registry, self._stack)
        if nav_id == nav_ids.ASSET_CATEGORIES:
            from seeker_accounting.modules.fixed_assets.ui.asset_categories_page import AssetCategoriesPage
            return AssetCategoriesPage(self._service_registry, self._stack)
        if nav_id == nav_ids.ASSETS:
            from seeker_accounting.modules.fixed_assets.ui.assets_page import AssetsPage
            return AssetsPage(self._service_registry, self._stack)
        if nav_id == nav_ids.DEPRECIATION_RUNS:
            from seeker_accounting.modules.fixed_assets.ui.depreciation_runs_page import DepreciationRunsPage
            return DepreciationRunsPage(self._service_registry, self._stack)
        if nav_id == nav_ids.CONTRACTS:
            from seeker_accounting.modules.contracts_projects.ui.contracts_page import ContractsPage
            return ContractsPage(self._service_registry, self._stack)
        if nav_id == nav_ids.PROJECTS:
            from seeker_accounting.modules.contracts_projects.ui.projects_page import ProjectsPage
            return ProjectsPage(self._service_registry, self._stack)
        if nav_id == nav_ids.PAYROLL_SETUP:
            from seeker_accounting.modules.payroll.ui.payroll_setup_page import PayrollSetupPage
            return PayrollSetupPage(self._service_registry, self._stack)
        if nav_id == nav_ids.PAYROLL_CALCULATION:
            from seeker_accounting.modules.payroll.ui.payroll_calculation_workspace import PayrollCalculationWorkspace
            return PayrollCalculationWorkspace(self._service_registry, self._stack)
        if nav_id == nav_ids.PAYROLL_ACCOUNTING:
            from seeker_accounting.modules.payroll.ui.payroll_accounting_workspace import PayrollAccountingWorkspace
            return PayrollAccountingWorkspace(self._service_registry, self._stack)
        if nav_id == nav_ids.PAYROLL_OPERATIONS:
            from seeker_accounting.modules.payroll.ui.payroll_operations_workspace import PayrollOperationsWorkspace
            return PayrollOperationsWorkspace(self._service_registry, self._stack)
        if nav_id == nav_ids.PROJECT_VARIANCE_ANALYSIS:
            from seeker_accounting.modules.management_reporting.ui.project_variance_analysis_page import ProjectVarianceAnalysisPage
            return ProjectVarianceAnalysisPage(self._service_registry, self._stack)
        if nav_id == nav_ids.CONTRACT_SUMMARY:
            from seeker_accounting.modules.management_reporting.ui.contract_summary_page import ContractSummaryPage
            return ContractSummaryPage(self._service_registry, self._stack)
        if nav_id == nav_ids.REPORTS:
            from seeker_accounting.modules.reporting.ui.reports_workspace import ReportsWorkspace
            return ReportsWorkspace(self._service_registry, self._stack)
        if nav_id == nav_ids.ADMINISTRATION:
            from seeker_accounting.modules.administration.ui.administration_page import AdministrationPage
            return AdministrationPage(self._service_registry, self._stack)
        if nav_id == nav_ids.ROLES:
            from seeker_accounting.modules.administration.ui.roles_page import RolesPage
            return RolesPage(self._service_registry, self._stack)
        if nav_id == nav_ids.AUDIT_LOG:
            from seeker_accounting.modules.audit.ui.audit_log_page import AuditLogPage
            return AuditLogPage(self._service_registry, self._stack)
        if nav_id == nav_ids.BACKUP_RESTORE:
            from seeker_accounting.modules.administration.ui.backup_restore_page import BackupRestorePage
            return BackupRestorePage(self._service_registry, self._stack)
        if nav_id == nav_ids.CUSTOMER_DETAIL:
            from seeker_accounting.modules.customers.ui.customer_detail_page import CustomerDetailPage
            return CustomerDetailPage(self._service_registry, self._stack)
        if nav_id == nav_ids.SUPPLIER_DETAIL:
            from seeker_accounting.modules.suppliers.ui.supplier_detail_page import SupplierDetailPage
            return SupplierDetailPage(self._service_registry, self._stack)
        if nav_id == nav_ids.ACCOUNT_DETAIL:
            from seeker_accounting.modules.accounting.chart_of_accounts.ui.account_detail_page import AccountDetailPage
            return AccountDetailPage(self._service_registry, self._stack)
        if nav_id == nav_ids.ITEM_DETAIL:
            from seeker_accounting.modules.inventory.ui.item_detail_page import ItemDetailPage
            return ItemDetailPage(self._service_registry, self._stack)
        if nav_id == nav_ids.SALES_INVOICE_DETAIL:
            from seeker_accounting.modules.sales.ui.sales_invoice_detail_page import SalesInvoiceDetailPage
            return SalesInvoiceDetailPage(self._service_registry, self._stack)
        if nav_id == nav_ids.PURCHASE_BILL_DETAIL:
            from seeker_accounting.modules.purchases.ui.purchase_bill_detail_page import PurchaseBillDetailPage
            return PurchaseBillDetailPage(self._service_registry, self._stack)
        return PlaceholderWorkspacePage(model, self._stack)
