from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from PySide6.QtCore import Qt
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
from seeker_accounting.modules.companies.dto.company_dto import ActiveCompanyDTO
from seeker_accounting.modules.inventory.dto.inventory_document_dto import InventoryDocumentListItemDTO
from seeker_accounting.modules.inventory.ui.inventory_document_dialog import InventoryDocumentDialog
from seeker_accounting.app.navigation.workflow_resume_service import ResumeTokenPayload
from seeker_accounting.platform.exceptions import NotFoundError, PeriodLockedError, ValidationError
from seeker_accounting.platform.exceptions.app_error_codes import AppErrorCode
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.table_helpers import configure_compact_table
from seeker_accounting.shared.workflow.document_sequence_preflight import (
    consume_resume_payload_for_workflows,
    handle_document_sequence_error,
    run_document_sequence_preflight,
)


class InventoryDocumentsPage(QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._documents: list[InventoryDocumentListItemDTO] = []
        self._pending_resume_payload: ResumeTokenPayload | None = None

        self.setObjectName("InventoryDocumentsPage")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_action_bar())
        root_layout.addWidget(self._build_content_stack(), 1)

        self._service_registry.active_company_context.active_company_changed.connect(
            self._handle_active_company_changed
        )
        self.reload_documents()

    # ------------------------------------------------------------------
    # Reload
    # ------------------------------------------------------------------

    def reload_documents(self, selected_document_id: int | None = None) -> None:
        active_company = self._active_company()

        if active_company is None:
            self._documents = []
            self._table.setRowCount(0)
            self._record_count_label.setText("Select a company")
            self._stack.setCurrentWidget(self._no_active_company_state)
            self._update_action_state()
            return

        try:
            self._documents = self._service_registry.inventory_document_service.list_inventory_documents(
                active_company.company_id,
                status_code=self._status_filter_value(),
                document_type_code=self._type_filter_value(),
            )
        except Exception as exc:
            self._documents = []
            self._table.setRowCount(0)
            self._record_count_label.setText("Unable to load")
            self._stack.setCurrentWidget(self._empty_state)
            self._update_action_state()
            show_error(self, "Inventory Documents", f"Document data could not be loaded.\n\n{exc}")
            return

        self._populate_table()
        self._apply_search_filter()
        self._sync_surface_state(active_company)
        self._restore_selection(selected_document_id)
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

        title = QLabel('Document Register', card)
        title.setObjectName("ToolbarTitle")
        layout.addWidget(title)

        self._record_count_label = QLabel(card)
        self._record_count_label.setObjectName("ToolbarMeta")
        layout.addWidget(self._record_count_label)

        layout.addStretch(1)
        self._search_input = QLineEdit(card)
        self._search_input.setPlaceholderText("Search documents...")
        self._search_input.setFixedWidth(180)
        self._search_input.textChanged.connect(lambda _text: self._apply_search_filter())
        layout.addWidget(self._search_input)

        self._status_filter_combo = QComboBox(card)
        self._status_filter_combo.addItem("All statuses", None)
        self._status_filter_combo.addItem("Draft", "draft")
        self._status_filter_combo.addItem("Posted", "posted")
        self._status_filter_combo.addItem("Cancelled", "cancelled")
        self._status_filter_combo.currentIndexChanged.connect(lambda _index: self.reload_documents())
        layout.addWidget(self._status_filter_combo)

        self._type_filter_combo = QComboBox(card)
        self._type_filter_combo.addItem("All types", None)
        self._type_filter_combo.addItem("Receipt", "receipt")
        self._type_filter_combo.addItem("Issue", "issue")
        self._type_filter_combo.addItem("Adjustment", "adjustment")
        self._type_filter_combo.currentIndexChanged.connect(lambda _index: self.reload_documents())
        layout.addWidget(self._type_filter_combo)

        self._new_button = QPushButton("New Document", card)
        self._new_button.setProperty("variant", "primary")
        self._new_button.clicked.connect(self._open_create_dialog)
        layout.addWidget(self._new_button)

        self._edit_button = QPushButton("Edit Draft", card)
        self._edit_button.setProperty("variant", "secondary")
        self._edit_button.clicked.connect(self._open_edit_dialog)
        layout.addWidget(self._edit_button)

        self._cancel_button = QPushButton("Cancel Draft", card)
        self._cancel_button.setProperty("variant", "secondary")
        self._cancel_button.clicked.connect(self._cancel_selected_draft)
        layout.addWidget(self._cancel_button)

        self._post_button = QPushButton("Post Document", card)
        self._post_button.setProperty("variant", "secondary")
        self._post_button.clicked.connect(self._post_selected_document)
        layout.addWidget(self._post_button)

        self._refresh_button = QPushButton("Refresh", card)
        self._refresh_button.setProperty("variant", "ghost")
        self._refresh_button.clicked.connect(lambda: self.reload_documents())
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
        self._table.setObjectName("InventoryDocumentsTable")
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels((
            "Document #",
            "Date",
            "Type",
            "Reference",
            "Total Value",
            "Status",
            "Posted At",
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

        title = QLabel("No inventory documents yet", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)

        summary = QLabel(
            "Create a receipt to add stock, an issue to consume stock, "
            "or an adjustment to correct quantities.",
            card,
        )
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        actions = QWidget(card)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 4, 0, 0)
        actions_layout.setSpacing(10)

        create_button = QPushButton("Create Document", actions)
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
            "Inventory documents are company-scoped. Choose the active company before creating documents.",
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
        if self._documents:
            self._stack.setCurrentWidget(self._table_surface)
            return
        self._stack.setCurrentWidget(self._empty_state)

    def _populate_table(self) -> None:
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)

        for doc in self._documents:
            row_index = self._table.rowCount()
            self._table.insertRow(row_index)
            values = (
                doc.document_number,
                self._format_date(doc.document_date),
                doc.document_type_code.title(),
                doc.reference_number or "",
                self._format_amount(doc.total_value),
                doc.status_code.title(),
                self._format_datetime(doc.posted_at),
            )
            for col, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if col == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, doc.id)
                if col in {1, 2, 4, 5, 6}:
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row_index, col, cell)

        self._table.resizeColumnsToContents()
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, header.ResizeMode.Stretch)
        header.setSectionResizeMode(4, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, header.ResizeMode.ResizeToContents)
        self._table.setSortingEnabled(True)

        count = len(self._documents)
        self._record_count_label.setText(f"{count} document" if count == 1 else f"{count} documents")

    def _apply_search_filter(self) -> None:
        query = self._search_input.text().strip().lower()
        for row in range(self._table.rowCount()):
            if not query:
                self._table.setRowHidden(row, False)
                continue
            match = False
            for col in range(self._table.columnCount()):
                cell = self._table.item(row, col)
                if cell is not None and query in cell.text().lower():
                    match = True
                    break
            self._table.setRowHidden(row, not match)

    def _restore_selection(self, selected_document_id: int | None) -> None:
        if self._table.rowCount() == 0:
            return
        if selected_document_id is None:
            self._table.selectRow(0)
            return
        for row in range(self._table.rowCount()):
            cell = self._table.item(row, 0)
            if cell is not None and cell.data(Qt.ItemDataRole.UserRole) == selected_document_id:
                self._table.selectRow(row)
                return
        self._table.selectRow(0)

    def _selected_document(self) -> InventoryDocumentListItemDTO | None:
        current_row = self._table.currentRow()
        if current_row < 0:
            return None
        cell = self._table.item(current_row, 0)
        if cell is None:
            return None
        doc_id = cell.data(Qt.ItemDataRole.UserRole)
        for doc in self._documents:
            if doc.id == doc_id:
                return doc
        return None

    def _update_action_state(self) -> None:
        active_company = self._active_company()
        selected = self._selected_document()
        has_company = active_company is not None
        is_draft = has_company and selected is not None and selected.status_code == "draft"

        self._new_button.setEnabled(has_company)
        self._edit_button.setEnabled(is_draft)
        self._cancel_button.setEnabled(is_draft)
        self._post_button.setEnabled(is_draft)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _open_create_dialog(self) -> None:
        active_company = self._active_company()
        if active_company is None:
            show_info(self, "Inventory Documents", "Select an active company first.")
            return
        if not run_document_sequence_preflight(
            self, self._service_registry,
            active_company.company_id, active_company.company_name,
            "inventory_document", nav_ids.INVENTORY_DOCUMENTS,
        ):
            return
        result = InventoryDocumentDialog.create_document(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            parent=self,
        )
        if result is not None:
            self.reload_documents(selected_document_id=result.id)

    def _open_edit_dialog(self) -> None:
        active_company = self._active_company()
        selected = self._selected_document()
        if active_company is None or selected is None:
            show_info(self, "Inventory Documents", "Select a draft document to edit.")
            return
        if selected.status_code != "draft":
            show_info(self, "Inventory Documents", "Only draft documents can be edited.")
            return
        result = InventoryDocumentDialog.edit_document(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            document_id=selected.id,
            parent=self,
        )
        if result is not None:
            self.reload_documents(selected_document_id=result.id)

    def _cancel_selected_draft(self) -> None:
        active_company = self._active_company()
        selected = self._selected_document()
        if active_company is None or selected is None:
            return

        choice = QMessageBox.question(
            self,
            "Cancel Draft Document",
            f"Cancel draft document {selected.document_number}?",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return

        try:
            self._service_registry.inventory_document_service.cancel_draft_document(
                active_company.company_id, selected.id
            )
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "Inventory Documents", str(exc))
            self.reload_documents(selected_document_id=selected.id)
            return
        self.reload_documents()

    def _post_selected_document(self) -> None:
        active_company = self._active_company()
        selected = self._selected_document()
        if active_company is None or selected is None:
            return

        choice = QMessageBox.question(
            self,
            "Post Document",
            (
                f"Post document {selected.document_number}?\n\n"
                "Posting creates a journal entry, updates cost layers, "
                "and makes the document immutable."
            ),
        )
        if choice != QMessageBox.StandardButton.Yes:
            return

        try:
            result = self._service_registry.inventory_posting_service.post_inventory_document(
                active_company.company_id,
                selected.id,
                actor_user_id=self._service_registry.app_context.current_user_id,
            )
        except ValidationError as exc:
            if exc.app_error_code == AppErrorCode.MISSING_DOCUMENT_SEQUENCE:
                handle_document_sequence_error(
                    self, self._service_registry, exc,
                    "inventory_document.post",
                    lambda: {"document_id": selected.id},
                    nav_ids.INVENTORY_DOCUMENTS,
                    active_company.company_name,
                )
                return
            show_error(self, "Inventory Documents", str(exc))
            self.reload_documents(selected_document_id=selected.id)
            return
        except (NotFoundError, PeriodLockedError) as exc:
            show_error(self, "Inventory Documents", str(exc))
            self.reload_documents(selected_document_id=selected.id)
            return

        show_info(
            self,
            "Inventory Documents",
            f"Document {result.document_number} posted successfully.\n"
            f"Journal entry: {result.journal_entry_number}",
        )
        self.reload_documents(selected_document_id=result.document_id)

    def _open_companies_workspace(self) -> None:
        self._service_registry.navigation_service.navigate(nav_ids.COMPANIES)

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    def _format_date(self, value: date) -> str:
        return value.strftime("%Y-%m-%d")

    def _format_datetime(self, value: datetime | None) -> str:
        return value.strftime("%Y-%m-%d %H:%M") if value is not None else ""

    def _format_amount(self, value: Decimal | None) -> str:
        if value is None:
            return ""
        return f"{value:,.2f}"

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    def _handle_item_double_clicked(self, *_args: object) -> None:
        selected = self._selected_document()
        if selected is None:
            return
        if selected.status_code == "draft":
            self._open_edit_dialog()

    def _handle_active_company_changed(self, company_id: object, company_name: object) -> None:
        _ = company_id, company_name
        self.reload_documents()

    def set_navigation_context(self, context: dict) -> None:
        from PySide6.QtCore import QTimer

        token_payload = consume_resume_payload_for_workflows(
            context=context,
            service_registry=self._service_registry,
            allowed_workflow_keys=("inventory_document.preflight", "inventory_document.post"),
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
        if payload.workflow_key == "inventory_document.post":
            document_id = payload.payload.get("document_id") if payload.payload else None
            self.reload_documents(selected_document_id=document_id)
            return
        self._open_create_dialog()
