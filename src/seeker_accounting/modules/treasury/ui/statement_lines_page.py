from __future__ import annotations

import logging

from datetime import date, datetime
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.modules.companies.dto.company_dto import ActiveCompanyDTO
from seeker_accounting.modules.treasury.dto.bank_statement_dto import BankStatementLineDTO
from seeker_accounting.modules.treasury.ui.manual_statement_line_dialog import ManualStatementLineDialog
from seeker_accounting.modules.treasury.ui.statement_import_dialog import StatementImportDialog
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError
from seeker_accounting.shared.ui.components import (
    DataTable,
    DataTableColumn,
    apply_status_chip_to_column,
)
from seeker_accounting.shared.ui.message_boxes import show_error, show_info

_log = logging.getLogger(__name__)


STATEMENT_LINE_COLUMNS: tuple[DataTableColumn, ...] = (
    DataTableColumn(key="date", title="Date"),
    DataTableColumn(key="value_date", title="Value Date"),
    DataTableColumn(key="description", title="Description"),
    DataTableColumn(key="reference", title="Reference"),
    DataTableColumn(key="debit", title="Debit", is_numeric=True),
    DataTableColumn(key="credit", title="Credit", is_numeric=True),
    DataTableColumn(key="reconciled", title="Reconciled"),
    DataTableColumn(key="batch", title="Batch"),
)


class StatementLinesPage(QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._lines: list[BankStatementLineDTO] = []

        self.setObjectName("StatementLinesPage")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_action_bar())
        root_layout.addWidget(self._build_content_stack(), 1)

        self._service_registry.active_company_context.active_company_changed.connect(
            self._handle_active_company_changed
        )
        self._load_account_filter()
        self.reload_lines()

    # ------------------------------------------------------------------
    # Reload
    # ------------------------------------------------------------------

    def reload_lines(self) -> None:
        active_company = self._active_company()

        if active_company is None:
            self._lines = []
            self._lines_model.removeRows(0, self._lines_model.rowCount())
            self._record_count_label.setText("Select a company")
            self._stack.setCurrentWidget(self._no_active_company_state)
            self._update_action_state()
            return

        financial_account_id = self._selected_financial_account_id()
        if financial_account_id is None:
            self._lines = []
            self._lines_model.removeRows(0, self._lines_model.rowCount())
            self._record_count_label.setText("Select an account")
            self._stack.setCurrentWidget(self._empty_state)
            self._update_action_state()
            return

        try:
            self._lines = self._service_registry.bank_statement_service.list_statement_lines(
                active_company.company_id,
                financial_account_id,
                reconciled_only=self._reconciled_filter_value(),
            )
        except Exception as exc:
            self._lines = []
            self._lines_model.removeRows(0, self._lines_model.rowCount())
            self._record_count_label.setText("Unable to load")
            self._stack.setCurrentWidget(self._empty_state)
            self._update_action_state()
            show_error(self, "Bank Statements", f"Statement lines could not be loaded.\n\n{exc}")
            return

        self._populate_table()
        self._sync_surface_state(active_company)
        self._update_record_count_label()
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

        title = QLabel('Statement Lines', card)
        title.setObjectName("ToolbarTitle")
        layout.addWidget(title)

        self._record_count_label = QLabel(card)
        self._record_count_label.setObjectName("ToolbarMeta")
        layout.addWidget(self._record_count_label)

        layout.addStretch(1)
        self._search_input = QLineEdit(card)
        self._search_input.setPlaceholderText("Search lines...")
        self._search_input.setFixedWidth(180)
        self._search_input.textChanged.connect(self._on_search_text_changed)
        layout.addWidget(self._search_input)

        self._account_filter_combo = QComboBox(card)
        self._account_filter_combo.currentIndexChanged.connect(lambda _index: self.reload_lines())
        layout.addWidget(self._account_filter_combo)

        self._reconciled_filter_combo = QComboBox(card)
        self._reconciled_filter_combo.addItem("All", None)
        self._reconciled_filter_combo.addItem("Reconciled", True)
        self._reconciled_filter_combo.addItem("Unreconciled", False)
        self._reconciled_filter_combo.currentIndexChanged.connect(lambda _index: self.reload_lines())
        layout.addWidget(self._reconciled_filter_combo)

        self._import_button = QPushButton("Import CSV", card)
        self._import_button.setProperty("variant", "primary")
        self._import_button.clicked.connect(self._open_import_dialog)
        layout.addWidget(self._import_button)

        self._add_manual_button = QPushButton("Add Manual Line", card)
        self._add_manual_button.setProperty("variant", "secondary")
        self._add_manual_button.clicked.connect(self._open_manual_line_dialog)
        layout.addWidget(self._add_manual_button)

        self._refresh_button = QPushButton("Refresh", card)
        self._refresh_button.setProperty("variant", "ghost")
        self._refresh_button.clicked.connect(lambda: self.reload_lines())
        layout.addWidget(self._refresh_button)
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

        self._lines_model = QStandardItemModel(0, len(STATEMENT_LINE_COLUMNS), self)
        self._lines_model.setHorizontalHeaderLabels(
            [c.title for c in STATEMENT_LINE_COLUMNS]
        )

        self._table = DataTable(
            columns=STATEMENT_LINE_COLUMNS,
            show_search=False,
            show_count=False,
            show_density_toggle=True,
            show_column_chooser=True,
            selection_mode="single",
            empty_state_text="No statement lines to display.",
            parent=card,
        )
        self._table.set_model(self._lines_model)
        self._lines_status_delegate = apply_status_chip_to_column(
            self._table.view(), 6
        )
        self._table.selection_changed.connect(self._on_selection_changed)
        layout.addWidget(self._table)
        return card

    def _build_empty_state(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)

        title = QLabel("Select a financial account to view statement lines", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)

        summary = QLabel(
            "Use the financial account filter above to choose an account. "
            "You can then import CSV statements or add manual lines.",
            card,
        )
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)
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
            "Bank statements are company-scoped. Choose the active company before importing or viewing statement lines.",
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

    def _selected_financial_account_id(self) -> int | None:
        data = self._account_filter_combo.currentData()
        if data is None or data == 0:
            return None
        return int(data)

    def _reconciled_filter_value(self) -> bool | None:
        value = self._reconciled_filter_combo.currentData()
        if isinstance(value, bool):
            return value
        return None

    def _sync_surface_state(self, active_company: ActiveCompanyDTO | None) -> None:
        if active_company is None:
            self._stack.setCurrentWidget(self._no_active_company_state)
            return
        if self._lines:
            self._stack.setCurrentWidget(self._table_surface)
            return
        self._stack.setCurrentWidget(self._empty_state)

    def _load_account_filter(self) -> None:
        self._account_filter_combo.blockSignals(True)
        self._account_filter_combo.clear()
        self._account_filter_combo.addItem("All accounts", 0)

        active_company = self._active_company()
        if active_company is not None:
            try:
                accounts = self._service_registry.financial_account_service.list_financial_accounts(
                    active_company.company_id, active_only=True
                )
                for acct in accounts:
                    self._account_filter_combo.addItem(
                        f"{acct.account_code} — {acct.name}", acct.id
                    )
            except Exception:
                _log.warning("Form data load error", exc_info=True)

        self._account_filter_combo.blockSignals(False)

    @staticmethod
    def _make_item(text, *, user_data=None) -> QStandardItem:
        item = QStandardItem("" if text is None else str(text))
        item.setEditable(False)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item

    @staticmethod
    def _make_numeric(value) -> QStandardItem:
        text = "" if value is None else f"{Decimal(str(value)):,.2f}"
        item = QStandardItem(text)
        item.setEditable(False)
        item.setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        return item

    def _populate_table(self) -> None:
        self._lines_model.removeRows(0, self._lines_model.rowCount())
        for line in self._lines:
            value_date = self._format_date(line.value_date) if line.value_date else ""
            batch = str(line.import_batch_id) if line.import_batch_id else "Manual"
            reconciled = "reconciled" if line.is_reconciled else "unreconciled"
            items = [
                self._make_item(self._format_date(line.line_date), user_data=line.id),
                self._make_item(value_date),
                self._make_item(line.description),
                self._make_item(line.reference or ""),
                self._make_numeric(line.debit_amount),
                self._make_numeric(line.credit_amount),
                self._make_item(reconciled),
                self._make_item(batch),
            ]
            self._lines_model.appendRow(items)

    def _on_search_text_changed(self, text: str) -> None:
        self._table.set_search_text(text)
        self._update_record_count_label()

    def _update_record_count_label(self) -> None:
        total = len(self._lines)
        query = self._search_input.text().strip()
        if query:
            proxy = self._table.view().model()
            visible = proxy.rowCount() if proxy is not None else total
            self._record_count_label.setText(
                f"{visible} shown of {total} lines"
            )
        else:
            self._record_count_label.setText(
                f"{total} line" if total == 1 else f"{total} lines"
            )

    def _on_selection_changed(self, _rows: list[int]) -> None:
        self._update_action_state()

    def _update_action_state(self) -> None:
        active_company = self._active_company()
        has_company = active_company is not None

        self._import_button.setEnabled(has_company)
        self._add_manual_button.setEnabled(has_company)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _open_import_dialog(self) -> None:
        active_company = self._active_company()
        if active_company is None:
            show_info(self, "Bank Statements", "Select an active company before importing statements.")
            return

        result = StatementImportDialog.import_statement(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            parent=self,
        )
        if result is not None:
            self.reload_lines()

    def _open_manual_line_dialog(self) -> None:
        active_company = self._active_company()
        if active_company is None:
            show_info(self, "Bank Statements", "Select an active company before adding statement lines.")
            return

        result = ManualStatementLineDialog.create_line(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            parent=self,
        )
        if result is not None:
            self.reload_lines()

    def _open_companies_workspace(self) -> None:
        self._service_registry.navigation_service.navigate(nav_ids.COMPANIES)

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    def _format_date(self, value: date) -> str:
        return value.strftime("%Y-%m-%d")

    def _format_amount(self, value: Decimal) -> str:
        return f"{value:,.2f}"

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    def _handle_active_company_changed(self, company_id: object, company_name: object) -> None:
        _ = company_id, company_name
        self._load_account_filter()
        self.reload_lines()
