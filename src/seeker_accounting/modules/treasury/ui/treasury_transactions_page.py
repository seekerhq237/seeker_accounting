from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
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
from seeker_accounting.app.shell.ribbon import RibbonHostMixin
from seeker_accounting.modules.companies.dto.company_dto import ActiveCompanyDTO
from seeker_accounting.modules.treasury.dto.treasury_transaction_dto import TreasuryTransactionListItemDTO
from seeker_accounting.modules.treasury.ui.treasury_transaction_dialog import TreasuryTransactionDialog
from seeker_accounting.app.navigation.workflow_resume_service import ResumeTokenPayload
from seeker_accounting.platform.exceptions import NotFoundError, PeriodLockedError, ValidationError
from seeker_accounting.platform.exceptions.app_error_codes import AppErrorCode
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.pager import Pager
from seeker_accounting.shared.ui.print_export_dialog import PrintExportDialog
from seeker_accounting.shared.ui.register import RegisterPage
from seeker_accounting.shared.ui.table_helpers import configure_dense_table
from seeker_accounting.shared.workflow.document_sequence_preflight import (
    consume_resume_payload_for_workflows,
    handle_document_sequence_error,
    run_document_sequence_preflight,
)


class TreasuryTransactionsPage(RibbonHostMixin, QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._transactions: list[TreasuryTransactionListItemDTO] = []
        self._total_count: int = 0
        self._pending_resume_payload: ResumeTokenPayload | None = None
        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(250)
        self._search_debounce.timeout.connect(lambda: self.reload_transactions(reset_page=True))

        self.setObjectName("TreasuryTransactionsPage")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._register = RegisterPage(self)
        self._populate_toolbar_strip(self._register)
        self._populate_action_band(self._register)
        self._register.action_band.hide()
        self._register.set_table_widget(self._build_content_stack())
        root_layout.addWidget(self._register)

        self._service_registry.active_company_context.active_company_changed.connect(
            self._handle_active_company_changed
        )
        self.reload_transactions()

    # ------------------------------------------------------------------
    # Reload
    # ------------------------------------------------------------------

    def reload_transactions(
        self,
        selected_transaction_id: int | None = None,
        reset_page: bool = False,
    ) -> None:
        active_company = self._active_company()

        if active_company is None:
            self._transactions = []
            self._total_count = 0
            self._table.setRowCount(0)
            self._record_count_label.setText("Select a company")
            self._pager.reset()
            self._stack.setCurrentWidget(self._no_active_company_state)
            self._update_action_state()
            return

        if reset_page:
            self._pager.reset()

        search_text = self._search_input.text().strip() or None
        try:
            page_result = self._service_registry.treasury_transaction_service.list_treasury_transactions_page(
                active_company.company_id,
                status_code=self._status_filter_value(),
                transaction_type_code=self._type_filter_value(),
                query=search_text,
                page=self._pager.page,
                page_size=self._pager.page_size,
            )
        except Exception as exc:
            self._transactions = []
            self._total_count = 0
            self._table.setRowCount(0)
            self._record_count_label.setText("Unable to load")
            self._pager.reset()
            self._stack.setCurrentWidget(self._empty_state)
            self._update_action_state()
            show_error(self, "Treasury Transactions", f"Transaction data could not be loaded.\n\n{exc}")
            return

        self._transactions = list(page_result.items)
        self._total_count = page_result.total_count
        self._pager.apply_result(page_result)
        self._populate_table()
        self._sync_surface_state(active_company)
        self._restore_selection(selected_transaction_id)
        self._update_action_state()

    def _handle_search_text_changed(self, _text: str) -> None:
        self._search_debounce.start()

    # ------------------------------------------------------------------
    # UI building
    # ------------------------------------------------------------------

    def _populate_toolbar_strip(self, register: RegisterPage) -> None:
        strip_layout = register.toolbar_strip_layout

        self._search_input = QLineEdit(register.toolbar_strip)
        self._search_input.setPlaceholderText("Search transactions…")
        self._search_input.setFixedWidth(200)
        self._search_input.textChanged.connect(self._handle_search_text_changed)
        strip_layout.addWidget(self._search_input)

        self._status_filter_combo = QComboBox(register.toolbar_strip)
        self._status_filter_combo.addItem("All statuses", None)
        self._status_filter_combo.addItem("Draft", "draft")
        self._status_filter_combo.addItem("Posted", "posted")
        self._status_filter_combo.addItem("Cancelled", "cancelled")
        self._status_filter_combo.currentIndexChanged.connect(lambda _index: self.reload_transactions(reset_page=True))
        strip_layout.addWidget(self._status_filter_combo)

        self._type_filter_combo = QComboBox(register.toolbar_strip)
        self._type_filter_combo.addItem("All types", None)
        self._type_filter_combo.addItem("Cash Receipt", "cash_receipt")
        self._type_filter_combo.addItem("Cash Payment", "cash_payment")
        self._type_filter_combo.addItem("Bank Receipt", "bank_receipt")
        self._type_filter_combo.addItem("Bank Payment", "bank_payment")
        self._type_filter_combo.currentIndexChanged.connect(lambda _index: self.reload_transactions(reset_page=True))
        strip_layout.addWidget(self._type_filter_combo)

        strip_layout.addStretch(1)

        self._record_count_label = QLabel(register.toolbar_strip)
        self._record_count_label.setObjectName("StatusRailText")
        strip_layout.addWidget(self._record_count_label)

        self._refresh_button = QPushButton("Refresh", register.toolbar_strip)
        self._refresh_button.setProperty("variant", "ghost")
        self._refresh_button.clicked.connect(lambda: self.reload_transactions())
        strip_layout.addWidget(self._refresh_button)

    def _populate_action_band(self, register: RegisterPage) -> None:
        band_layout = register.action_band_layout

        self._new_button = QPushButton("New Transaction", register.action_band)
        self._new_button.setProperty("variant", "primary")
        self._new_button.clicked.connect(self._open_create_dialog)
        band_layout.addWidget(self._new_button)

        self._edit_button = QPushButton("Edit Draft", register.action_band)
        self._edit_button.setProperty("variant", "secondary")
        self._edit_button.clicked.connect(self._open_edit_dialog)
        band_layout.addWidget(self._edit_button)

        self._cancel_button = QPushButton("Cancel Draft", register.action_band)
        self._cancel_button.setProperty("variant", "secondary")
        self._cancel_button.clicked.connect(self._cancel_selected_draft)
        band_layout.addWidget(self._cancel_button)

        self._post_button = QPushButton("Post Transaction", register.action_band)
        self._post_button.setProperty("variant", "secondary")
        self._post_button.clicked.connect(self._post_selected_transaction)
        band_layout.addWidget(self._post_button)

        band_layout.addStretch(1)

        self._print_button = QPushButton("Print / Export", register.action_band)
        self._print_button.setProperty("variant", "ghost")
        self._print_button.clicked.connect(self._print_selected_transaction)
        band_layout.addWidget(self._print_button)

        self._export_list_button = QPushButton("Export List", register.action_band)
        self._export_list_button.setProperty("variant", "ghost")
        self._export_list_button.clicked.connect(self._export_transaction_list)
        band_layout.addWidget(self._export_list_button)

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
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._table = QTableWidget(container)
        self._table.setObjectName("TreasuryTransactionsTable")
        self._table.setColumnCount(8)
        self._table.setHorizontalHeaderLabels((
            "Transaction #",
            "Type",
            "Date",
            "Account",
            "Currency",
            "Total",
            "Status",
            "Posted At",
        ))
        configure_dense_table(self._table)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.itemSelectionChanged.connect(self._update_action_state)
        self._table.itemDoubleClicked.connect(self._handle_item_double_clicked)
        layout.addWidget(self._table, 1)

        self._pager = Pager(container, default_page_size=100)
        self._pager.page_changed.connect(lambda _p: self.reload_transactions())
        self._pager.page_size_changed.connect(lambda _s: self.reload_transactions(reset_page=True))
        layout.addWidget(self._pager)
        return container

    def _build_empty_state(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)

        title = QLabel("No treasury transactions yet", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)

        summary = QLabel(
            "Create the first treasury transaction to record a cash or bank receipt or payment, "
            "then post when the transaction is complete.",
            card,
        )
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        actions = QWidget(card)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 4, 0, 0)
        actions_layout.setSpacing(10)

        create_button = QPushButton("Create Transaction", actions)
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
            "Treasury transactions are company-scoped. Choose the active company before creating or posting transactions.",
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

    def _type_filter_value(self) -> str | None:
        value = self._type_filter_combo.currentData()
        return value if isinstance(value, str) and value else None

    def _sync_surface_state(self, active_company: ActiveCompanyDTO | None) -> None:
        if active_company is None:
            self._stack.setCurrentWidget(self._no_active_company_state)
            return
        if self._transactions:
            self._stack.setCurrentWidget(self._table_surface)
            return
        self._stack.setCurrentWidget(self._empty_state)

    def _populate_table(self) -> None:
        self._table.setUpdatesEnabled(False)
        self._table.setSortingEnabled(False)
        try:
            self._table.setRowCount(len(self._transactions))
            for row_index, txn in enumerate(self._transactions):
                values = (
                    txn.transaction_number,
                    txn.transaction_type_code.replace("_", " ").title(),
                    self._format_date(txn.transaction_date),
                    txn.financial_account_name,
                    txn.currency_code,
                    self._format_amount(txn.total_amount),
                    txn.status_code.title(),
                    self._format_datetime(txn.posted_at),
                )
                for col, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    if col == 0:
                        item.setData(Qt.ItemDataRole.UserRole, txn.id)
                    if col in {2, 4, 6, 7}:
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if col == 5:
                        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    self._table.setItem(row_index, col, item)

            self._table.resizeColumnsToContents()
            header = self._table.horizontalHeader()
            header.setSectionResizeMode(0, header.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(1, header.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(2, header.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(3, header.ResizeMode.Stretch)
            header.setSectionResizeMode(4, header.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(5, header.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(6, header.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(7, header.ResizeMode.ResizeToContents)
        finally:
            self._table.setSortingEnabled(True)
            self._table.setUpdatesEnabled(True)

        search_text = self._search_input.text().strip()
        total = self._total_count
        shown = len(self._transactions)
        if search_text:
            self._record_count_label.setText(f"{shown} shown of {total} matches")
        else:
            self._record_count_label.setText(
                f"{total} transaction" if total == 1 else f"{total} transactions"
            )

    def _apply_search_filter(self) -> None:
        # Search is now handled server-side via reload_transactions. Kept as a
        # no-op for backward compatibility with any external callers.
        return

    def _restore_selection(self, selected_transaction_id: int | None) -> None:
        if self._table.rowCount() == 0:
            return
        if selected_transaction_id is None:
            self._table.selectRow(0)
            return
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == selected_transaction_id:
                self._table.selectRow(row)
                return
        self._table.selectRow(0)

    def _selected_transaction(self) -> TreasuryTransactionListItemDTO | None:
        current_row = self._table.currentRow()
        if current_row < 0:
            return None
        item = self._table.item(current_row, 0)
        if item is None:
            return None
        transaction_id = item.data(Qt.ItemDataRole.UserRole)
        for txn in self._transactions:
            if txn.id == transaction_id:
                return txn
        return None

    def _update_action_state(self) -> None:
        active_company = self._active_company()
        selected = self._selected_transaction()
        has_company = active_company is not None
        is_draft = has_company and selected is not None and selected.status_code == "draft"

        self._new_button.setEnabled(has_company)
        self._edit_button.setEnabled(is_draft)
        self._cancel_button.setEnabled(is_draft)
        self._post_button.setEnabled(is_draft)
        self._print_button.setEnabled(has_company and selected is not None)
        self._export_list_button.setEnabled(has_company and bool(self._transactions))
        self._notify_ribbon_state_changed()

    # ── IRibbonHost ───────────────────────────────────────────────────

    def _ribbon_commands(self):
        return {
            "treasury_transactions.new": self._open_create_dialog,
            "treasury_transactions.edit": self._open_edit_dialog,
            "treasury_transactions.cancel": self._cancel_selected_draft,
            "treasury_transactions.post": self._post_selected_transaction,
            "treasury_transactions.refresh": self.reload_transactions,
            "treasury_transactions.print": self._print_selected_transaction,
            "treasury_transactions.export_list": self._export_transaction_list,
        }

    def ribbon_state(self):
        return {
            "treasury_transactions.new": self._new_button.isEnabled(),
            "treasury_transactions.edit": self._edit_button.isEnabled(),
            "treasury_transactions.cancel": self._cancel_button.isEnabled(),
            "treasury_transactions.post": self._post_button.isEnabled(),
            "treasury_transactions.refresh": True,
            "treasury_transactions.print": self._print_button.isEnabled(),
            "treasury_transactions.export_list": self._export_list_button.isEnabled(),
        }

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _print_selected_transaction(self) -> None:
        active_company = self._active_company()
        if active_company is None:
            return
        selected = self._selected_transaction()
        if selected is None:
            return
        result = PrintExportDialog.show_dialog(self, f"Treasury Transaction — {selected.transaction_number}")
        if result is None:
            return
        try:
            self._service_registry.treasury_transaction_print_service.print_transaction(
                active_company.company_id, selected.id, result,
            )
            result.open_file()
        except Exception as exc:
            show_error(self, "Treasury Transactions", f"Export failed.\n\n{exc}")

    def _export_transaction_list(self) -> None:
        active_company = self._active_company()
        if active_company is None or not self._transactions:
            return
        result = PrintExportDialog.show_dialog(self, "Treasury Transaction Register")
        if result is None:
            return
        try:
            self._service_registry.treasury_transaction_print_service.print_transaction_list(
                active_company.company_id, self._transactions, result,
            )
            result.open_file()
        except Exception as exc:
            show_error(self, "Treasury Transactions", f"Export failed.\n\n{exc}")

    def _open_create_dialog(self) -> None:
        active_company = self._active_company()
        if active_company is None:
            show_info(self, "Treasury Transactions", "Select an active company before creating transactions.")
            return
        if not run_document_sequence_preflight(
            self, self._service_registry,
            active_company.company_id, active_company.company_name,
            "treasury_transaction", nav_ids.TREASURY_TRANSACTIONS,
        ):
            return

        result = TreasuryTransactionDialog.create_transaction(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            parent=self,
        )
        if result is not None:
            self.reload_transactions(selected_transaction_id=result.id)

    def _open_edit_dialog(self) -> None:
        active_company = self._active_company()
        selected = self._selected_transaction()
        if active_company is None or selected is None:
            show_info(self, "Treasury Transactions", "Select a draft transaction to edit.")
            return
        if selected.status_code != "draft":
            show_info(self, "Treasury Transactions", "Only draft transactions can be edited.")
            return

        result = TreasuryTransactionDialog.edit_transaction(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            transaction_id=selected.id,
            parent=self,
        )
        if result is not None:
            self.reload_transactions(selected_transaction_id=result.id)

    def _cancel_selected_draft(self) -> None:
        active_company = self._active_company()
        selected = self._selected_transaction()
        if active_company is None or selected is None:
            show_info(self, "Treasury Transactions", "Select a draft transaction to cancel.")
            return

        choice = QMessageBox.question(
            self,
            "Cancel Draft Transaction",
            f"Cancel draft transaction {selected.transaction_number}?",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return

        try:
            self._service_registry.treasury_transaction_service.cancel_draft_transaction(
                active_company.company_id, selected.id
            )
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "Treasury Transactions", str(exc))
            self.reload_transactions(selected_transaction_id=selected.id)
            return
        self.reload_transactions()

    def _post_selected_transaction(self) -> None:
        active_company = self._active_company()
        selected = self._selected_transaction()
        if active_company is None or selected is None:
            show_info(self, "Treasury Transactions", "Select a draft transaction to post.")
            return

        choice = QMessageBox.question(
            self,
            "Post Transaction",
            (
                f"Post transaction {selected.transaction_number}?\n\n"
                "Posting creates a journal entry, assigns a final transaction number, "
                "and makes the transaction immutable."
            ),
        )
        if choice != QMessageBox.StandardButton.Yes:
            return

        try:
            result = self._service_registry.treasury_transaction_posting_service.post_transaction(
                active_company.company_id,
                selected.id,
                actor_user_id=self._service_registry.app_context.current_user_id,
            )
        except ValidationError as exc:
            if exc.app_error_code == AppErrorCode.MISSING_DOCUMENT_SEQUENCE:
                handle_document_sequence_error(
                    self, self._service_registry, exc,
                    "treasury_transaction.post",
                    lambda: {"document_id": selected.id},
                    nav_ids.TREASURY_TRANSACTIONS,
                    active_company.company_name,
                )
                return
            show_error(self, "Treasury Transactions", str(exc))
            self.reload_transactions(selected_transaction_id=selected.id)
            return
        except (NotFoundError, PeriodLockedError) as exc:
            show_error(self, "Treasury Transactions", str(exc))
            self.reload_transactions(selected_transaction_id=selected.id)
            return

        show_info(
            self,
            "Treasury Transactions",
            f"Transaction {result.transaction_number} posted successfully.\n"
            f"Journal entry: {result.journal_entry_number}",
        )
        self.reload_transactions(selected_transaction_id=result.transaction_id)

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

    def _handle_item_double_clicked(self, *_args: object) -> None:
        selected = self._selected_transaction()
        if selected is None:
            return
        if selected.status_code == "draft":
            self._open_edit_dialog()

    def _handle_active_company_changed(self, company_id: object, company_name: object) -> None:
        _ = company_id, company_name
        self.reload_transactions()

    def set_navigation_context(self, context: dict) -> None:
        from PySide6.QtCore import QTimer

        token_payload = consume_resume_payload_for_workflows(
            context=context,
            service_registry=self._service_registry,
            allowed_workflow_keys=("treasury_transaction.preflight", "treasury_transaction.post"),
        )
        if token_payload is None:
            self._pending_resume_payload = None
            return
        self._pending_resume_payload = token_payload
        QTimer.singleShot(0, self._open_from_resume_payload)

    def _open_from_resume_payload(self) -> None:
        payload = self._pending_resume_payload
        if payload is None:
            return
        self._pending_resume_payload = None
        active_company = self._active_company()
        if active_company is None:
            return
        if payload.workflow_key == "treasury_transaction.post":
            document_id = payload.payload.get("document_id") if payload.payload else None
            self.reload_transactions(selected_transaction_id=document_id)
            return
        self._open_create_dialog()
