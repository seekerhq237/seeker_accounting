from __future__ import annotations

import logging

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
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
from seeker_accounting.modules.treasury.dto.bank_reconciliation_commands import CreateReconciliationSessionCommand
from seeker_accounting.modules.treasury.dto.bank_reconciliation_dto import ReconciliationSessionListItemDTO
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.table_helpers import configure_compact_table

_log = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Inline create-session dialog
# ------------------------------------------------------------------

class _CreateSessionDialog(QDialog):
    """Collects the data required to create a new bank reconciliation session."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._company_id = company_id

        self.setWindowTitle("New Reconciliation Session")
        self.setMinimumWidth(420)

        layout = QFormLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Financial account
        self._account_combo = QComboBox(self)
        self._load_financial_accounts()
        layout.addRow("Financial Account", self._account_combo)

        # Statement end date
        self._statement_end_date = QDateEdit(self)
        self._statement_end_date.setCalendarPopup(True)
        self._statement_end_date.setDate(date.today())
        self._statement_end_date.setDisplayFormat("yyyy-MM-dd")
        layout.addRow("Statement End Date", self._statement_end_date)

        # Statement ending balance
        self._ending_balance_input = QLineEdit(self)
        self._ending_balance_input.setPlaceholderText("0.00")
        layout.addRow("Ending Balance", self._ending_balance_input)

        # Notes
        self._notes_input = QPlainTextEdit(self)
        self._notes_input.setMaximumHeight(80)
        self._notes_input.setPlaceholderText("Optional notes...")
        layout.addRow("Notes", self._notes_input)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)

    # -- helpers --

    def _load_financial_accounts(self) -> None:
        try:
            accounts = self._service_registry.financial_account_service.list_financial_accounts(
                self._company_id, active_only=True
            )
        except Exception:
            accounts = []
        for acct in accounts:
            self._account_combo.addItem(f"{acct.account_code} — {acct.name}", acct.id)

    def _on_accept(self) -> None:
        if self._account_combo.currentIndex() < 0:
            show_error(self, "Reconciliation", "Select a financial account.")
            return

        balance_text = self._ending_balance_input.text().strip()
        try:
            ending_balance = Decimal(balance_text)
        except (InvalidOperation, ValueError):
            show_error(self, "Reconciliation", "Enter a valid numeric ending balance.")
            return

        self.command = CreateReconciliationSessionCommand(
            financial_account_id=self._account_combo.currentData(),
            statement_end_date=self._statement_end_date.date().toPython(),
            statement_ending_balance=ending_balance,
            notes=self._notes_input.toPlainText().strip() or None,
        )
        self.accept()


# ------------------------------------------------------------------
# Main page
# ------------------------------------------------------------------

class BankReconciliationPage(QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._sessions: list[ReconciliationSessionListItemDTO] = []

        self.setObjectName("BankReconciliationPage")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_action_bar())
        root_layout.addWidget(self._build_content_stack(), 1)

        self._service_registry.active_company_context.active_company_changed.connect(
            self._handle_active_company_changed
        )
        self.reload_sessions()

    # ------------------------------------------------------------------
    # Reload
    # ------------------------------------------------------------------

    def reload_sessions(self, selected_session_id: int | None = None) -> None:
        active_company = self._active_company()

        if active_company is None:
            self._sessions = []
            self._table.setRowCount(0)
            self._record_count_label.setText("Select a company")
            self._stack.setCurrentWidget(self._no_active_company_state)
            self._update_action_state()
            return

        try:
            self._sessions = self._service_registry.bank_reconciliation_service.list_reconciliation_sessions(
                active_company.company_id,
                financial_account_id=None,
            )
        except Exception as exc:
            self._sessions = []
            self._table.setRowCount(0)
            self._record_count_label.setText("Unable to load")
            self._stack.setCurrentWidget(self._empty_state)
            self._update_action_state()
            show_error(self, "Bank Reconciliation", f"Session data could not be loaded.\n\n{exc}")
            return

        self._populate_table()
        self._apply_search_filter()
        self._sync_surface_state(active_company)
        self._restore_selection(selected_session_id)
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

        title = QLabel('Reconciliation Sessions', card)
        title.setObjectName("ToolbarTitle")
        layout.addWidget(title)

        self._record_count_label = QLabel(card)
        self._record_count_label.setObjectName("ToolbarMeta")
        layout.addWidget(self._record_count_label)

        layout.addStretch(1)
        self._search_input = QLineEdit(card)
        self._search_input.setPlaceholderText("Search sessions...")
        self._search_input.setFixedWidth(180)
        self._search_input.textChanged.connect(lambda _text: self._apply_search_filter())
        layout.addWidget(self._search_input)

        self._status_filter_combo = QComboBox(card)
        self._status_filter_combo.addItem("All statuses", None)
        self._status_filter_combo.addItem("Draft", "draft")
        self._status_filter_combo.addItem("Completed", "completed")
        self._status_filter_combo.currentIndexChanged.connect(lambda _index: self.reload_sessions())
        layout.addWidget(self._status_filter_combo)

        self._new_button = QPushButton("New Session", card)
        self._new_button.setProperty("variant", "primary")
        self._new_button.clicked.connect(self._open_create_dialog)
        layout.addWidget(self._new_button)

        self._complete_button = QPushButton("Complete Session", card)
        self._complete_button.setProperty("variant", "secondary")
        self._complete_button.clicked.connect(self._complete_selected_session)
        layout.addWidget(self._complete_button)

        self._summary_button = QPushButton("View Summary", card)
        self._summary_button.setProperty("variant", "secondary")
        self._summary_button.clicked.connect(self._view_summary)
        layout.addWidget(self._summary_button)

        self._refresh_button = QPushButton("Refresh", card)
        self._refresh_button.setProperty("variant", "ghost")
        self._refresh_button.clicked.connect(lambda: self.reload_sessions())
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
        self._table = QTableWidget(card)
        self._table.setObjectName("BankReconciliationTable")
        self._table.setColumnCount(8)
        self._table.setHorizontalHeaderLabels((
            "ID",
            "Account",
            "Statement End Date",
            "Ending Balance",
            "Matches",
            "Status",
            "Completed At",
            "Created At",
        ))
        configure_compact_table(self._table)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.itemSelectionChanged.connect(self._update_action_state)
        layout.addWidget(self._table)
        return card

    def _build_empty_state(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)

        title = QLabel("No reconciliation sessions yet", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)

        summary = QLabel(
            "Create a reconciliation session to begin matching bank statement lines "
            "against recorded transactions for a financial account.",
            card,
        )
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        actions = QWidget(card)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 4, 0, 0)
        actions_layout.setSpacing(10)

        create_button = QPushButton("New Session", actions)
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
            "Bank reconciliation is company-scoped. Choose the active company before managing reconciliation sessions.",
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

    def _status_filter_value(self) -> str | None:
        value = self._status_filter_combo.currentData()
        return value if isinstance(value, str) and value else None

    def _sync_surface_state(self, active_company: ActiveCompanyDTO | None) -> None:
        if active_company is None:
            self._stack.setCurrentWidget(self._no_active_company_state)
            return
        if self._sessions:
            self._stack.setCurrentWidget(self._table_surface)
            return
        self._stack.setCurrentWidget(self._empty_state)

    def _populate_table(self) -> None:
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)

        for session in self._sessions:
            row_index = self._table.rowCount()
            self._table.insertRow(row_index)
            values = (
                str(session.id),
                session.financial_account_name,
                self._format_date(session.statement_end_date),
                self._format_amount(session.statement_ending_balance),
                str(session.match_count),
                session.status_code.title(),
                self._format_datetime(session.completed_at),
                self._format_datetime(session.created_at),
            )
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, session.id)
                # Right-align numeric columns: Ending Balance (3), Matches (4)
                if col in {3, 4}:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                # Center-align: ID (0), Statement End Date (2), Status (5), Completed At (6), Created At (7)
                if col in {0, 2, 5, 6, 7}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row_index, col, item)

        self._table.resizeColumnsToContents()
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, header.ResizeMode.Stretch)
        header.setSectionResizeMode(2, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, header.ResizeMode.ResizeToContents)
        self._table.setSortingEnabled(True)

        count = len(self._sessions)
        self._record_count_label.setText(f"{count} session" if count == 1 else f"{count} sessions")

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

    def _restore_selection(self, selected_session_id: int | None) -> None:
        if self._table.rowCount() == 0:
            return
        if selected_session_id is None:
            self._table.selectRow(0)
            return
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == selected_session_id:
                self._table.selectRow(row)
                return
        self._table.selectRow(0)

    def _selected_session(self) -> ReconciliationSessionListItemDTO | None:
        current_row = self._table.currentRow()
        if current_row < 0:
            return None
        item = self._table.item(current_row, 0)
        if item is None:
            return None
        session_id = item.data(Qt.ItemDataRole.UserRole)
        for s in self._sessions:
            if s.id == session_id:
                return s
        return None

    def _update_action_state(self) -> None:
        active_company = self._active_company()
        selected = self._selected_session()
        has_company = active_company is not None
        is_draft = has_company and selected is not None and selected.status_code == "draft"
        has_selection = has_company and selected is not None

        self._new_button.setEnabled(has_company)
        self._complete_button.setEnabled(is_draft)
        self._summary_button.setEnabled(has_selection)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _open_create_dialog(self) -> None:
        active_company = self._active_company()
        if active_company is None:
            show_info(self, "Bank Reconciliation", "Select an active company before creating sessions.")
            return

        dialog = _CreateSessionDialog(
            self._service_registry,
            company_id=active_company.company_id,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            result = self._service_registry.bank_reconciliation_service.create_reconciliation_session(
                active_company.company_id,
                dialog.command,
                actor_user_id=self._service_registry.app_context.current_user_id,
            )
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "Bank Reconciliation", str(exc))
            return

        self.reload_sessions(selected_session_id=result.id)

    def _complete_selected_session(self) -> None:
        active_company = self._active_company()
        selected = self._selected_session()
        if active_company is None or selected is None:
            show_info(self, "Bank Reconciliation", "Select a draft session to complete.")
            return

        choice = QMessageBox.question(
            self,
            "Complete Reconciliation Session",
            f"Complete reconciliation session #{selected.id} for {selected.financial_account_name}?\n\n"
            "This marks the session as completed and cannot be undone.",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return

        try:
            self._service_registry.bank_reconciliation_service.complete_session(
                active_company.company_id,
                selected.id,
                actor_user_id=self._service_registry.app_context.current_user_id,
            )
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "Bank Reconciliation", str(exc))
            self.reload_sessions(selected_session_id=selected.id)
            return

        self.reload_sessions(selected_session_id=selected.id)

    def _view_summary(self) -> None:
        active_company = self._active_company()
        selected = self._selected_session()
        if active_company is None or selected is None:
            show_info(self, "Bank Reconciliation", "Select a session to view its summary.")
            return

        try:
            summary = self._service_registry.bank_reconciliation_service.get_reconciliation_summary(
                active_company.company_id,
                selected.id,
            )
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "Bank Reconciliation", str(exc))
            return

        QMessageBox.information(
            self,
            "Reconciliation Summary",
            (
                f"Session #{selected.id} — {selected.financial_account_name}\n\n"
                f"Matched statement lines: {summary.matched_statement_count}\n"
                f"Unmatched statement lines: {summary.unmatched_statement_count}\n"
                f"Total matched amount: {summary.total_matched_amount:,.2f}"
            ),
        )

    def _open_companies_workspace(self) -> None:
        self._service_registry.navigation_service.navigate(nav_ids.COMPANIES)

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    def _format_date(self, value: date) -> str:
        return value.strftime("%Y-%m-%d")

    def _format_datetime(self, value: datetime | None) -> str:
        return value.strftime("%Y-%m-%d %H:%M") if value is not None else ""

    def _format_amount(self, value: Decimal) -> str:
        return f"{value:,.2f}"

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    def _handle_active_company_changed(self, company_id: object, company_name: object) -> None:
        _ = company_id, company_name
        self.reload_sessions()
