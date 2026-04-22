from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.modules.companies.dto.company_dto import ActiveCompanyDTO
from seeker_accounting.modules.treasury.dto.financial_account_dto import FinancialAccountListItemDTO
from seeker_accounting.modules.treasury.ui.financial_account_dialog import FinancialAccountDialog
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.print_export_dialog import PrintExportDialog
from seeker_accounting.shared.ui.table_helpers import configure_compact_table


class FinancialAccountsPage(QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._accounts: list[FinancialAccountListItemDTO] = []

        self.setObjectName("FinancialAccountsPage")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(16)

        root_layout.addWidget(self._build_action_bar())
        root_layout.addWidget(self._build_content_stack(), 1)

        self._service_registry.active_company_context.active_company_changed.connect(
            self._handle_active_company_changed
        )
        self.reload_accounts()

    # ------------------------------------------------------------------
    # Reload
    # ------------------------------------------------------------------

    def reload_accounts(self, selected_account_id: int | None = None) -> None:
        active_company = self._active_company()

        if active_company is None:
            self._accounts = []
            self._table.setRowCount(0)
            self._record_count_label.setText("Select a company")
            self._stack.setCurrentWidget(self._no_active_company_state)
            self._update_action_state()
            return

        try:
            self._accounts = self._service_registry.financial_account_service.list_financial_accounts(
                active_company.company_id,
            )
        except Exception as exc:
            self._accounts = []
            self._table.setRowCount(0)
            self._record_count_label.setText("Unable to load")
            self._stack.setCurrentWidget(self._empty_state)
            self._update_action_state()
            show_error(self, "Financial Accounts", f"Account data could not be loaded.\n\n{exc}")
            return

        self._populate_table()
        self._apply_search_filter()
        self._sync_surface_state(active_company)
        self._restore_selection(selected_account_id)
        self._update_action_state()

    # ------------------------------------------------------------------
    # UI building
    # ------------------------------------------------------------------

    def _build_action_bar(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageToolbar")
        card.setProperty("card", True)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(12)

        self._search_input = QLineEdit(card)
        self._search_input.setPlaceholderText("Search accounts...")
        self._search_input.setFixedWidth(180)
        self._search_input.textChanged.connect(lambda _text: self._apply_search_filter())
        layout.addWidget(self._search_input)

        self._new_button = QPushButton("New Account", card)
        self._new_button.setProperty("variant", "primary")
        self._new_button.clicked.connect(self._open_create_dialog)
        layout.addWidget(self._new_button)

        self._edit_button = QPushButton("Edit", card)
        self._edit_button.setProperty("variant", "secondary")
        self._edit_button.clicked.connect(self._open_edit_dialog)
        layout.addWidget(self._edit_button)

        self._toggle_active_button = QPushButton("Toggle Active", card)
        self._toggle_active_button.setProperty("variant", "secondary")
        self._toggle_active_button.clicked.connect(self._toggle_active)
        layout.addWidget(self._toggle_active_button)

        self._refresh_button = QPushButton("Refresh", card)
        self._refresh_button.setProperty("variant", "ghost")
        self._refresh_button.clicked.connect(lambda: self.reload_accounts())
        layout.addWidget(self._refresh_button)

        self._export_list_button = QPushButton("Export List", card)
        self._export_list_button.setProperty("variant", "ghost")
        self._export_list_button.clicked.connect(self._export_account_list)
        layout.addWidget(self._export_list_button)
        return card

    def _build_content_stack(self) -> QWidget:
        self._stack = QStackedWidget(self)
        self._table_surface = self._build_table_surface()
        self._empty_state = self._build_empty_state()
        self._no_active_company_state = self._build_no_active_company_state()
        self._stack.addWidget(self._table_surface)
        self._stack.addWidget(self._empty_state)
        self._stack.addWidget(self._no_active_company_state)
        return self._stack

    def _build_table_surface(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(12)

        top_row = QWidget(card)
        top_row_layout = QHBoxLayout(top_row)
        top_row_layout.setContentsMargins(0, 0, 0, 0)
        top_row_layout.setSpacing(12)

        title = QLabel("Account Register", top_row)
        title.setObjectName("CardTitle")
        top_row_layout.addWidget(title)
        top_row_layout.addStretch(1)

        self._record_count_label = QLabel(top_row)
        self._record_count_label.setObjectName("ToolbarMeta")
        top_row_layout.addWidget(self._record_count_label)

        layout.addWidget(top_row)

        self._table = QTableWidget(card)
        self._table.setObjectName("FinancialAccountsTable")
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels((
            "Code",
            "Name",
            "Type",
            "GL Account",
            "Currency",
            "Active",
            "Updated At",
        ))
        configure_compact_table(self._table)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.itemSelectionChanged.connect(self._update_action_state)
        self._table.itemDoubleClicked.connect(self._handle_item_double_clicked)
        layout.addWidget(self._table)
        return card

    def _build_empty_state(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)

        title = QLabel("No financial accounts yet", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)

        summary = QLabel(
            "Create the first financial account for the active company to begin managing "
            "bank and cash positions.",
            card,
        )
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        actions = QWidget(card)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 4, 0, 0)
        actions_layout.setSpacing(10)

        create_button = QPushButton("Create Account", actions)
        create_button.setProperty("variant", "primary")
        create_button.clicked.connect(self._open_create_dialog)
        actions_layout.addWidget(create_button, 0, Qt.AlignmentFlag.AlignLeft)
        actions_layout.addStretch(1)

        layout.addWidget(actions)
        layout.addStretch(1)
        return card

    def _build_no_active_company_state(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)

        title = QLabel("Select an active company first", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)

        summary = QLabel(
            "Financial accounts are company-scoped. Choose the active company before managing accounts.",
            card,
        )
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        actions = QWidget(card)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 4, 0, 0)
        actions_layout.setSpacing(10)

        companies_button = QPushButton("Open Companies", actions)
        companies_button.setProperty("variant", "secondary")
        companies_button.clicked.connect(self._open_companies_workspace)
        actions_layout.addWidget(companies_button, 0, Qt.AlignmentFlag.AlignLeft)
        actions_layout.addStretch(1)

        layout.addWidget(actions)
        layout.addStretch(1)
        return card

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _active_company(self) -> ActiveCompanyDTO | None:
        return self._service_registry.company_context_service.get_active_company()

    def _sync_surface_state(self, active_company: ActiveCompanyDTO | None) -> None:
        if active_company is None:
            self._stack.setCurrentWidget(self._no_active_company_state)
            return
        if self._accounts:
            self._stack.setCurrentWidget(self._table_surface)
            return
        self._stack.setCurrentWidget(self._empty_state)

    def _populate_table(self) -> None:
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)

        for acct in self._accounts:
            row_index = self._table.rowCount()
            self._table.insertRow(row_index)
            values = (
                acct.account_code,
                acct.name,
                acct.financial_account_type_code.replace("_", " ").title(),
                f"{acct.gl_account_code} — {acct.gl_account_name}",
                acct.currency_code,
                "Active" if acct.is_active else "Inactive",
                self._format_datetime(acct.updated_at),
            )
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, acct.id)
                if col in {2, 4, 5, 6}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row_index, col, item)

        self._table.resizeColumnsToContents()
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, header.ResizeMode.Stretch)
        header.setSectionResizeMode(1, header.ResizeMode.Stretch)
        header.setSectionResizeMode(2, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, header.ResizeMode.ResizeToContents)
        self._table.setSortingEnabled(True)

        count = len(self._accounts)
        self._record_count_label.setText(f"{count} account" if count == 1 else f"{count} accounts")

    def _apply_search_filter(self) -> None:
        query = self._search_input.text().strip().lower()
        for row in range(self._table.rowCount()):
            if not query:
                self._table.setRowHidden(row, False)
                continue
            match = False
            for col in range(self._table.columnCount()):
                item = self._table.item(row, col)
                if item is not None and query in item.text().lower():
                    match = True
                    break
            self._table.setRowHidden(row, not match)

    def _restore_selection(self, selected_account_id: int | None) -> None:
        if self._table.rowCount() == 0:
            return
        if selected_account_id is None:
            self._table.selectRow(0)
            return
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == selected_account_id:
                self._table.selectRow(row)
                return
        self._table.selectRow(0)

    def _selected_account(self) -> FinancialAccountListItemDTO | None:
        current_row = self._table.currentRow()
        if current_row < 0:
            return None
        item = self._table.item(current_row, 0)
        if item is None:
            return None
        account_id = item.data(Qt.ItemDataRole.UserRole)
        for acct in self._accounts:
            if acct.id == account_id:
                return acct
        return None

    def _update_action_state(self) -> None:
        active_company = self._active_company()
        selected = self._selected_account()
        has_company = active_company is not None

        self._new_button.setEnabled(has_company)
        self._edit_button.setEnabled(has_company and selected is not None)
        self._toggle_active_button.setEnabled(has_company and selected is not None)
        self._export_list_button.setEnabled(has_company and bool(self._accounts))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _export_account_list(self) -> None:
        active_company = self._active_company()
        if active_company is None or not self._accounts:
            return
        result = PrintExportDialog.show_dialog(self, "Financial Account Register")
        if result is None:
            return
        try:
            self._service_registry.financial_account_print_service.print_account_list(
                active_company.company_id, self._accounts, result,
            )
            result.open_file()
        except Exception as exc:
            show_error(self, "Financial Accounts", f"Export failed.\n\n{exc}")

    def _open_create_dialog(self) -> None:
        active_company = self._active_company()
        if active_company is None:
            show_info(self, "Financial Accounts", "Select an active company before creating accounts.")
            return

        result = FinancialAccountDialog.create_account(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            parent=self,
        )
        if result is not None:
            self.reload_accounts(selected_account_id=result.id)

    def _open_edit_dialog(self) -> None:
        active_company = self._active_company()
        selected = self._selected_account()
        if active_company is None or selected is None:
            show_info(self, "Financial Accounts", "Select an account to edit.")
            return

        result = FinancialAccountDialog.edit_account(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            account_id=selected.id,
            parent=self,
        )
        if result is not None:
            self.reload_accounts(selected_account_id=result.id)

    def _toggle_active(self) -> None:
        active_company = self._active_company()
        selected = self._selected_account()
        if active_company is None or selected is None:
            show_info(self, "Financial Accounts", "Select an account to toggle.")
            return

        new_state = not selected.is_active
        action_label = "activate" if new_state else "deactivate"

        choice = QMessageBox.question(
            self,
            "Toggle Active Status",
            f"Are you sure you want to {action_label} account '{selected.account_code} — {selected.name}'?",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return

        try:
            self._service_registry.financial_account_service.toggle_active(
                active_company.company_id, selected.id, is_active=new_state
            )
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "Financial Accounts", str(exc))
            self.reload_accounts(selected_account_id=selected.id)
            return

        self.reload_accounts(selected_account_id=selected.id)

    def _open_companies_workspace(self) -> None:
        self._service_registry.navigation_service.navigate(nav_ids.COMPANIES)

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    def _format_datetime(self, value: datetime | None) -> str:
        return value.strftime("%Y-%m-%d %H:%M") if value is not None else ""

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    def _handle_item_double_clicked(self, *_args: object) -> None:
        selected = self._selected_account()
        if selected is not None:
            self._open_edit_dialog()

    def _handle_active_company_changed(self, company_id: object, company_name: object) -> None:
        _ = company_id, company_name
        self.reload_accounts()
