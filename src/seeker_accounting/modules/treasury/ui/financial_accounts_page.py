from __future__ import annotations

import logging

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.modules.companies.dto.company_dto import ActiveCompanyDTO
from seeker_accounting.modules.treasury.dto.financial_account_dto import FinancialAccountListItemDTO
from seeker_accounting.modules.treasury.ui.financial_account_dialog import FinancialAccountDialog
from seeker_accounting.platform.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from seeker_accounting.shared.ui.components import (
    DataTable,
    DataTableColumn,
    apply_status_chip_to_column,
)
from seeker_accounting.shared.ui.empty_states import build_empty_state
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.print_export_dialog import PrintExportDialog


FINANCIAL_ACCOUNT_COLUMNS: tuple[DataTableColumn, ...] = (
    DataTableColumn(key="account_code", title="Code"),
    DataTableColumn(key="name", title="Name"),
    DataTableColumn(key="type", title="Type"),
    DataTableColumn(key="gl_account", title="GL Account"),
    DataTableColumn(key="currency", title="Currency"),
    DataTableColumn(key="active", title="Active"),
    DataTableColumn(key="updated_at", title="Updated At"),
)


_log = logging.getLogger(__name__)


class FinancialAccountsPage(QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._accounts: list[FinancialAccountListItemDTO] = []

        self.setObjectName("FinancialAccountsPage")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

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
            self._accounts_model.removeRows(0, self._accounts_model.rowCount())
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
            self._accounts_model.removeRows(0, self._accounts_model.rowCount())
            self._record_count_label.setText("Unable to load")
            self._stack.setCurrentWidget(self._empty_state)
            self._update_action_state()
            show_error(self, "Financial Accounts", f"Account data could not be loaded.\n\n{exc}")
            return

        self._populate_table()
        self._sync_surface_state(active_company)
        self._update_record_count_label()
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
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)

        title = QLabel('Account Register', card)
        title.setObjectName("ToolbarTitle")
        layout.addWidget(title)

        self._record_count_label = QLabel(card)
        self._record_count_label.setObjectName("ToolbarMeta")
        layout.addWidget(self._record_count_label)

        layout.addStretch(1)
        self._search_input = QLineEdit(card)
        self._search_input.setPlaceholderText("Search accounts...")
        self._search_input.setFixedWidth(180)
        self._search_input.textChanged.connect(self._on_search_text_changed)
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
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._accounts_model = QStandardItemModel(0, len(FINANCIAL_ACCOUNT_COLUMNS), self)
        self._accounts_model.setHorizontalHeaderLabels(
            [c.title for c in FINANCIAL_ACCOUNT_COLUMNS]
        )

        self._table = DataTable(
            columns=FINANCIAL_ACCOUNT_COLUMNS,
            show_search=False,
            show_count=False,
            show_density_toggle=True,
            show_column_chooser=True,
            selection_mode="single",
            empty_state_text="No financial accounts to display.",
            parent=card,
        )
        self._table.set_model(self._accounts_model)
        self._accounts_status_delegate = apply_status_chip_to_column(
            self._table.view(), 5
        )
        self._table.selection_changed.connect(self._on_selection_changed)
        self._table.row_activated.connect(self._on_row_activated)
        layout.addWidget(self._table)
        return card

    def _build_empty_state(self) -> QWidget:
        state = build_empty_state("treasury.financial_accounts.empty", parent=self)
        state.primary_clicked.connect(self._open_create_dialog)
        return state

    def _build_no_active_company_state(self) -> QWidget:
        state = build_empty_state("treasury.no_company", parent=self)
        state.primary_clicked.connect(self._open_companies_workspace)
        return state

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _active_company(self) -> ActiveCompanyDTO | None:
        return self._service_registry.company_context_service.get_active_company()

    def _show_permission_denied(self, permission_code: str) -> None:
        show_error(
            self,
            "Permission Denied",
            self._service_registry.permission_service.build_denied_message(permission_code),
        )

    def _sync_surface_state(self, active_company: ActiveCompanyDTO | None) -> None:
        if active_company is None:
            self._stack.setCurrentWidget(self._no_active_company_state)
            return
        if self._accounts:
            self._stack.setCurrentWidget(self._table_surface)
            return
        self._stack.setCurrentWidget(self._empty_state)

    @staticmethod
    def _make_item(text, *, user_data=None) -> QStandardItem:
        item = QStandardItem("" if text is None else str(text))
        item.setEditable(False)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item

    def _populate_table(self) -> None:
        self._accounts_model.removeRows(0, self._accounts_model.rowCount())
        for acct in self._accounts:
            type_label = acct.financial_account_type_code.replace("_", " ").title()
            gl_label = f"{acct.gl_account_code} — {acct.gl_account_name}"
            items = [
                self._make_item(acct.account_code, user_data=acct.id),
                self._make_item(acct.name),
                self._make_item(type_label),
                self._make_item(gl_label),
                self._make_item(acct.currency_code),
                self._make_item("active" if acct.is_active else "inactive"),
                self._make_item(self._format_datetime(acct.updated_at)),
            ]
            self._accounts_model.appendRow(items)

    def _on_search_text_changed(self, text: str) -> None:
        self._table.set_search_text(text)
        self._update_record_count_label()

    def _update_record_count_label(self) -> None:
        total = len(self._accounts)
        query = self._search_input.text().strip()
        if query:
            proxy = self._table.view().model()
            visible = proxy.rowCount() if proxy is not None else total
            self._record_count_label.setText(
                f"{visible} shown of {total} accounts"
            )
        else:
            self._record_count_label.setText(
                f"{total} account" if total == 1 else f"{total} accounts"
            )

    def _restore_selection(self, selected_account_id: int | None) -> None:
        if not self._accounts:
            return
        if selected_account_id is None:
            target_idx = 0
        else:
            target_idx = next(
                (i for i, a in enumerate(self._accounts) if a.id == selected_account_id),
                0,
            )
        proxy = self._table.view().model()
        if proxy is None:
            return
        src_index = self._accounts_model.index(target_idx, 0)
        proxy_index = proxy.mapFromSource(src_index)
        if not proxy_index.isValid():
            return
        sm = self._table.view().selectionModel()
        if sm is None:
            return
        sm.select(
            proxy_index,
            sm.SelectionFlag.ClearAndSelect | sm.SelectionFlag.Rows,
        )
        self._table.view().scrollTo(proxy_index)

    def _selected_account(self) -> FinancialAccountListItemDTO | None:
        rows = self._table.selected_rows()
        if not rows:
            return None
        idx = rows[0]
        if 0 <= idx < len(self._accounts):
            return self._accounts[idx]
        return None

    def _on_selection_changed(self, _rows: list[int]) -> None:
        self._update_action_state()

    def _on_row_activated(self, _row: int) -> None:
        if self._selected_account() is not None:
            self._open_edit_dialog()

    def _update_action_state(self) -> None:
        active_company = self._active_company()
        selected = self._selected_account()
        has_company = active_company is not None
        perm = self._service_registry.permission_service

        self._new_button.setEnabled(has_company and perm.has_permission("treasury.financial_accounts.create"))
        self._edit_button.setEnabled(has_company and selected is not None and perm.has_permission("treasury.financial_accounts.edit"))
        self._toggle_active_button.setEnabled(has_company and selected is not None and perm.has_permission("treasury.financial_accounts.deactivate"))
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
        except AppError as exc:
            show_error(self, "Financial Accounts", f"Export failed.\n\n{exc}")

        except Exception:
            _log.exception("Financial Accounts")
            show_error(self, "Financial Accounts", "An unexpected error occurred. See application log for details.")

    def _open_create_dialog(self) -> None:
        if not self._service_registry.permission_service.has_permission("treasury.financial_accounts.create"):
            self._show_permission_denied("treasury.financial_accounts.create")
            return
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
        if not self._service_registry.permission_service.has_permission("treasury.financial_accounts.edit"):
            self._show_permission_denied("treasury.financial_accounts.edit")
            return
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
        if not self._service_registry.permission_service.has_permission("treasury.financial_accounts.deactivate"):
            self._show_permission_denied("treasury.financial_accounts.deactivate")
            return
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

    def _handle_active_company_changed(self, company_id: object, company_name: object) -> None:
        _ = company_id, company_name
        self.reload_accounts()
