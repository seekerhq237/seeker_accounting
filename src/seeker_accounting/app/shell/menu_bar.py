"""Shell menu bar — Operational Desktop top menu band.

Thin, native-style QMenuBar that exposes the core application actions
as an always-visible band above the command band. All actions are
wired to existing services / navigation so this is a surface, not a
new command source.
"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMenuBar, QWidget

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.shared.ui.layout_constraints import apply_window_size


class ShellMenuBar(QMenuBar):
    """Top menu band. File / Edit / View / Records / Reports / Tools / Help."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        *,
        show_command_palette: Callable[[], None] | None = None,
        toggle_sidebar: Callable[[], None] | None = None,
        logout_requested: Callable[[], None] | None = None,
        show_help: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._sr = service_registry
        self._show_command_palette = show_command_palette
        self._toggle_sidebar = toggle_sidebar
        self._logout_requested = logout_requested
        self._show_help = show_help

        self.setObjectName("ShellMenuBar")
        self.setNativeMenuBar(False)

        self._build_file_menu()
        self._build_edit_menu()
        self._build_view_menu()
        self._build_records_menu()
        self._build_reports_menu()
        self._build_tools_menu()
        self._build_help_menu()

    # ── Menus ──────────────────────────────────────────────────────────

    def _build_file_menu(self) -> None:
        menu = self.addMenu("&File")
        menu.addAction(self._nav_action("&Dashboard", nav_ids.DASHBOARD, "Ctrl+Home"))
        menu.addAction(self._nav_action("Manage &Companies", nav_ids.COMPANIES))
        menu.addSeparator()
        menu.addAction(self._nav_action("Organisation &Settings", nav_ids.ORGANISATION_SETTINGS))
        menu.addAction(self._nav_action("&Backup && Restore", nav_ids.BACKUP_RESTORE))
        menu.addSeparator()
        logout = QAction("Sign &Out", self)
        logout.triggered.connect(self._emit_logout)
        menu.addAction(logout)
        quit_action = QAction("E&xit", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self._quit_application)
        menu.addAction(quit_action)

    def _build_edit_menu(self) -> None:
        menu = self.addMenu("&Edit")
        find = QAction("&Find…", self)
        find.setShortcut(QKeySequence("Ctrl+F"))
        if self._show_command_palette is not None:
            find.triggered.connect(self._show_command_palette)
        else:
            find.setEnabled(False)
        menu.addAction(find)
        palette = QAction("Command &Palette…", self)
        palette.setShortcut(QKeySequence("Ctrl+K"))
        if self._show_command_palette is not None:
            palette.triggered.connect(self._show_command_palette)
        else:
            palette.setEnabled(False)
        menu.addAction(palette)

    def _build_view_menu(self) -> None:
        menu = self.addMenu("&View")
        toggle = QAction("Toggle &Navigation", self)
        toggle.setShortcut(QKeySequence("Ctrl+B"))
        if self._toggle_sidebar is not None:
            toggle.triggered.connect(self._toggle_sidebar)
        else:
            toggle.setEnabled(False)
        menu.addAction(toggle)
        menu.addSeparator()
        theme = QAction("Switch &Theme", self)
        theme.triggered.connect(self._toggle_theme)
        menu.addAction(theme)

    def _build_records_menu(self) -> None:
        menu = self.addMenu("&Records")

        # Accounting
        acct = menu.addMenu("&Accounting")
        acct.addAction(self._nav_action("Chart of Accounts", nav_ids.CHART_OF_ACCOUNTS))
        acct.addAction(self._nav_action("Journals", nav_ids.JOURNALS))
        acct.addAction(self._nav_action("Fiscal Periods", nav_ids.FISCAL_PERIODS))
        acct.addAction(self._nav_action("Account Role Mappings", nav_ids.ACCOUNT_ROLE_MAPPINGS))
        acct.addAction(self._nav_action("Deferrals", nav_ids.DEFERRALS))

        # Sales
        sales = menu.addMenu("&Sales")
        sales.addAction(self._nav_action("Customers", nav_ids.CUSTOMERS))
        sales.addAction(self._nav_action("Quotes", nav_ids.CUSTOMER_QUOTES))
        sales.addAction(self._nav_action("Sales Orders", nav_ids.SALES_ORDERS))
        sales.addAction(self._nav_action("Sales Invoices", nav_ids.SALES_INVOICES))
        sales.addAction(self._nav_action("Credit Notes", nav_ids.SALES_CREDIT_NOTES))
        sales.addAction(self._nav_action("Receipts", nav_ids.CUSTOMER_RECEIPTS))

        # Purchases
        purch = menu.addMenu("&Purchases")
        purch.addAction(self._nav_action("Suppliers", nav_ids.SUPPLIERS))
        purch.addAction(self._nav_action("Purchase Orders", nav_ids.PURCHASE_ORDERS))
        purch.addAction(self._nav_action("Bills", nav_ids.PURCHASE_BILLS))
        purch.addAction(self._nav_action("Credit Notes", nav_ids.PURCHASE_CREDIT_NOTES))
        purch.addAction(self._nav_action("Payments", nav_ids.SUPPLIER_PAYMENTS))

        # Banking & Treasury
        bank = menu.addMenu("&Banking && Treasury")
        bank.addAction(self._nav_action("Financial Accounts", nav_ids.FINANCIAL_ACCOUNTS))
        bank.addAction(self._nav_action("Transactions", nav_ids.TREASURY_TRANSACTIONS))
        bank.addAction(self._nav_action("Transfers", nav_ids.TREASURY_TRANSFERS))
        bank.addAction(self._nav_action("Bank Reconciliation", nav_ids.BANK_RECONCILIATION))

        # Inventory
        inv = menu.addMenu("&Inventory")
        inv.addAction(self._nav_action("Items", nav_ids.ITEMS))
        inv.addAction(self._nav_action("Categories", nav_ids.ITEM_CATEGORIES))
        inv.addAction(self._nav_action("Documents", nav_ids.INVENTORY_DOCUMENTS))
        inv.addAction(self._nav_action("Locations", nav_ids.INVENTORY_LOCATIONS))
        inv.addAction(self._nav_action("Stock Position", nav_ids.STOCK_POSITION))
        inv.addAction(self._nav_action("Price Lists", nav_ids.PRICE_LISTS))

        # Fixed Assets
        fa = menu.addMenu("Fixed &Assets")
        fa.addAction(self._nav_action("Assets", nav_ids.ASSETS))
        fa.addAction(self._nav_action("Asset Categories", nav_ids.ASSET_CATEGORIES))
        fa.addAction(self._nav_action("Depreciation Runs", nav_ids.DEPRECIATION_RUNS))

        # Payroll
        pay = menu.addMenu("&Payroll")
        pay.addAction(self._nav_action("Payroll Workbench", nav_ids.PAYROLL_WORKBENCH))
        pay.addAction(self._nav_action("Payroll Setup", nav_ids.PAYROLL_SETUP))

        # Contracts & Projects
        cp = menu.addMenu("&Contracts && Projects")
        cp.addAction(self._nav_action("Contracts", nav_ids.CONTRACTS))
        cp.addAction(self._nav_action("Projects", nav_ids.PROJECTS))

        # Reference Data
        ref = menu.addMenu("&Reference Data")
        ref.addAction(self._nav_action("Payment Terms", nav_ids.PAYMENT_TERMS))
        ref.addAction(self._nav_action("Tax Codes", nav_ids.TAX_CODES))
        ref.addAction(self._nav_action("Document Sequences", nav_ids.DOCUMENT_SEQUENCES))
        ref.addAction(self._nav_action("Units of Measure", nav_ids.UNITS_OF_MEASURE))

    def _build_reports_menu(self) -> None:
        menu = self.addMenu("&Reports")
        menu.addAction(self._nav_action("Report Centre", nav_ids.REPORTS))
        menu.addSeparator()

        # Inventory
        inv = menu.addMenu("&Inventory")
        inv.addAction(self._nav_action("Inventory Reports", nav_ids.INVENTORY_REPORTS))
        inv.addAction(self._nav_action("Stock Position", nav_ids.STOCK_POSITION))
        inv.addAction(self._nav_action("Reorder Planning", nav_ids.REORDER_PLANNING))

        # Fixed Assets
        fa = menu.addMenu("Fixed &Assets")
        fa.addAction(self._nav_action("Asset Register", nav_ids.ASSETS))
        fa.addAction(self._nav_action("Depreciation Runs", nav_ids.DEPRECIATION_RUNS))

        # Payroll
        pay = menu.addMenu("&Payroll")
        pay.addAction(self._nav_action("Payroll Operations", nav_ids.PAYROLL_OPERATIONS))

        # Contracts & Projects
        cp = menu.addMenu("&Contracts && Projects")
        cp.addAction(self._nav_action("Project Variance Analysis", nav_ids.PROJECT_VARIANCE_ANALYSIS))
        cp.addAction(self._nav_action("Contract Summary", nav_ids.CONTRACT_SUMMARY))

        # Tax
        tax = menu.addMenu("&Tax")
        tax.addAction(self._nav_action("Tax Dashboard", nav_ids.TAX_DASHBOARD))
        tax.addAction(self._nav_action("Tax Compliance", nav_ids.TAX_COMPLIANCE))
        tax.addAction(self._nav_action("Tax Audit Trail", nav_ids.TAX_AUDIT_TRAIL))
        tax.addAction(self._nav_action("Withholding Certificates", nav_ids.WITHHOLDING_CERTIFICATES))

    def _build_tools_menu(self) -> None:
        menu = self.addMenu("&Tools")

        # Administration submenu
        admin = menu.addMenu("&Administration")
        admin.addAction(self._nav_action("Users", nav_ids.ADMINISTRATION))
        admin.addAction(self._nav_action("Roles", nav_ids.ROLES))
        admin.addAction(self._nav_action("Audit Log", nav_ids.AUDIT_LOG))

        menu.addSeparator()
        menu.addAction(self._nav_action("Organisation &Settings", nav_ids.ORGANISATION_SETTINGS))
        menu.addAction(self._nav_action("&Backup && Restore", nav_ids.BACKUP_RESTORE))

    def _build_help_menu(self) -> None:
        menu = self.addMenu("&Help")

        help_topics = QAction("Help &Topics", self)
        help_topics.setShortcut(QKeySequence("F1"))
        if self._show_help is not None:
            help_topics.triggered.connect(self._show_help)
        else:
            help_topics.setEnabled(False)
        menu.addAction(help_topics)

        shortcuts = QAction("&Keyboard Shortcuts", self)
        shortcuts.setShortcut(QKeySequence("Ctrl+/"))
        shortcuts.triggered.connect(self._show_keyboard_shortcuts)
        menu.addAction(shortcuts)

        menu.addSeparator()
        about = QAction("&About Seeker Accounting", self)
        about.triggered.connect(self._show_about)
        menu.addAction(about)

    # ── Action helpers ────────────────────────────────────────────────

    def _nav_action(self, label: str, nav_id: str, shortcut: str | None = None) -> QAction:
        action = QAction(label, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(lambda _checked=False, target=nav_id: self._navigate(target))
        return action

    def _navigate(self, nav_id: str) -> None:
        try:
            self._sr.navigation_service.navigate(nav_id)
        except Exception:
            # Nav errors surface through the standard nav flow; menu must not crash.
            pass

    def _emit_logout(self) -> None:
        if self._logout_requested is not None:
            self._logout_requested()

    def _quit_application(self) -> None:
        window = self.window()
        if window is not None:
            window.close()

    def _toggle_theme(self) -> None:
        try:
            self._sr.theme_manager.toggle_theme()
        except Exception:
            pass

    def _show_keyboard_shortcuts(self) -> None:
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout

        dlg = QDialog(self.window())
        dlg.setWindowTitle("Keyboard Shortcuts")
        apply_window_size(dlg, "app.shell.menu.bar.keyboard.shortcuts.0")
        browser = QTextBrowser(dlg)
        browser.setHtml(
            "<style>"
            "body{font-family:sans-serif;font-size:13px;margin:8px}"
            "h3{margin:10px 0 4px;color:#666;font-size:12px;text-transform:uppercase;letter-spacing:1px}"
            "table{border-collapse:collapse;width:100%}"
            "td{padding:4px 8px}"
            "td:first-child{font-family:monospace;color:#0078d4;min-width:150px}"
            "</style>"
            "<h3>Navigation</h3>"
            "<table>"
            "<tr><td>Ctrl+Home</td><td>Dashboard</td></tr>"
            "<tr><td>Ctrl+B</td><td>Toggle Navigation Panel</td></tr>"
            "</table>"
            "<h3>Search &amp; Commands</h3>"
            "<table>"
            "<tr><td>Ctrl+F</td><td>Find</td></tr>"
            "<tr><td>Ctrl+K</td><td>Command Palette</td></tr>"
            "</table>"
            "<h3>Help</h3>"
            "<table>"
            "<tr><td>F1</td><td>Help Topics (current page)</td></tr>"
            "<tr><td>Ctrl+/</td><td>Keyboard Shortcuts</td></tr>"
            "</table>"
            "<h3>Application</h3>"
            "<table>"
            "<tr><td>Alt+F4</td><td>Exit</td></tr>"
            "</table>"
        )
        layout = QVBoxLayout(dlg)
        layout.addWidget(browser)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, dlg)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        dlg.exec()

    def _show_about(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        settings = self._sr.settings
        QMessageBox.about(
            self.window(),
            "About",
            f"<b>{settings.window_title}</b><br>Seeker Accounting.",
        )
