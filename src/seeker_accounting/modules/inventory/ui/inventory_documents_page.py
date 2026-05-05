from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
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
from seeker_accounting.modules.inventory.dto.inventory_document_commands import (
    CancelInventoryDocumentCommand,
    ReverseInventoryDocumentCommand,
    SubmitInventoryDocumentCommand,
)
from seeker_accounting.modules.inventory.dto.inventory_document_dto import InventoryDocumentListItemDTO
from seeker_accounting.modules.inventory.ui.inventory_document_dialog import InventoryDocumentDialog
from seeker_accounting.app.navigation.workflow_resume_service import ResumeTokenPayload
from seeker_accounting.platform.exceptions import NotFoundError, PeriodLockedError, PermissionDeniedError, ValidationError
from seeker_accounting.platform.exceptions.app_error_codes import AppErrorCode
from seeker_accounting.shared.ui.components import (
    DataTable,
    DataTableColumn,
    apply_status_chip_to_column,
)
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.workflow.document_sequence_preflight import (
    consume_resume_payload_for_workflows,
    handle_document_sequence_error,
    run_document_sequence_preflight,
)


INVENTORY_DOCUMENT_COLUMNS: tuple[DataTableColumn, ...] = (
    DataTableColumn(key="document_number", title="Document #"),
    DataTableColumn(key="document_date", title="Date"),
    DataTableColumn(key="document_type", title="Type"),
    DataTableColumn(key="reference", title="Reference"),
    DataTableColumn(key="total_value", title="Total Value"),
    DataTableColumn(key="status", title="Status"),
    DataTableColumn(key="posted_at", title="Posted At"),
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
            self._model.removeRows(0, self._model.rowCount())
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
            self._model.removeRows(0, self._model.rowCount())
            self._record_count_label.setText("Unable to load")
            self._stack.setCurrentWidget(self._empty_state)
            self._update_action_state()
            show_error(self, "Inventory Documents", f"Document data could not be loaded.\n\n{exc}")
            return

        self._populate_table()
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
        self._search_input.textChanged.connect(self._on_search_text_changed)
        layout.addWidget(self._search_input)

        self._status_filter_combo = QComboBox(card)
        self._status_filter_combo.addItem("All statuses", None)
        self._status_filter_combo.addItem("Draft", "draft")
        self._status_filter_combo.addItem("Pending Posting", "pending_posting")
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

        self._submit_button = QPushButton("Submit", card)
        self._submit_button.setProperty("variant", "secondary")
        self._submit_button.clicked.connect(self._submit_selected_document)
        layout.addWidget(self._submit_button)

        self._post_button = QPushButton("Post Document", card)
        self._post_button.setProperty("variant", "secondary")
        self._post_button.clicked.connect(self._post_selected_document)
        layout.addWidget(self._post_button)

        self._reverse_button = QPushButton("Reverse", card)
        self._reverse_button.setProperty("variant", "secondary")
        self._reverse_button.clicked.connect(self._reverse_selected_document)
        layout.addWidget(self._reverse_button)

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

        self._model = QStandardItemModel(0, len(INVENTORY_DOCUMENT_COLUMNS), self)
        self._model.setHorizontalHeaderLabels([c.title for c in INVENTORY_DOCUMENT_COLUMNS])

        self._table = DataTable(
            columns=INVENTORY_DOCUMENT_COLUMNS,
            show_search=False,
            show_count=False,
            show_density_toggle=True,
            show_column_chooser=True,
            selection_mode="single",
            empty_state_text="No inventory documents to display.",
            parent=card,
        )
        self._table.set_model(self._model)
        self._status_delegate = apply_status_chip_to_column(self._table.view(), 5)
        self._table.selection_changed.connect(lambda _rows: self._update_action_state())
        self._table.row_activated.connect(self._on_row_activated)
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

    def _show_permission_denied(self, permission_code: str) -> None:
        show_error(
            self,
            "Permission Denied",
            self._service_registry.permission_service.build_denied_message(permission_code),
        )

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
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return item

    def _populate_table(self) -> None:
        self._model.removeRows(0, self._model.rowCount())

        for doc in self._documents:
            type_label = doc.document_type_code.replace("_", " ").title()
            row_items = [
                self._make_item(doc.document_number, user_data=doc.id),
                self._make_item(self._format_date(doc.document_date)),
                self._make_item(type_label),
                self._make_item(doc.reference_number or ""),
                self._make_numeric(doc.total_value),
                self._make_item(doc.status_code or ""),
                self._make_item(self._format_datetime(doc.posted_at)),
            ]
            self._model.appendRow(row_items)

        count = len(self._documents)
        self._record_count_label.setText(f"{count} document" if count == 1 else f"{count} documents")

    def _on_search_text_changed(self, text: str) -> None:
        self._table.set_search_text(text)

    def _restore_selection(self, selected_document_id: int | None) -> None:
        if not self._documents:
            return
        if selected_document_id is None:
            target_idx = 0
        else:
            target_idx = next(
                (i for i, d in enumerate(self._documents) if d.id == selected_document_id),
                0,
            )
        proxy = self._table.view().model()
        if proxy is None:
            return
        src_index = self._model.index(target_idx, 0)
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

    def _selected_document(self) -> InventoryDocumentListItemDTO | None:
        rows = self._table.selected_rows()
        if not rows:
            return None
        idx = rows[0]
        if 0 <= idx < len(self._documents):
            return self._documents[idx]
        return None

    def _on_row_activated(self, _row: int) -> None:
        self._handle_item_double_clicked()

    def _update_action_state(self) -> None:
        active_company = self._active_company()
        selected = self._selected_document()
        has_company = active_company is not None
        is_draft = has_company and selected is not None and selected.status_code == "draft"
        can_post = has_company and selected is not None and selected.status_code in {"draft", "pending_posting"}
        can_reverse = (
            has_company
            and selected is not None
            and selected.status_code == "posted"
            and selected.reversal_document_id is None
            and selected.reversal_of_document_id is None
        )
        perm = self._service_registry.permission_service

        self._new_button.setEnabled(has_company and perm.has_permission("inventory.documents.create"))
        self._edit_button.setEnabled(is_draft and perm.has_permission("inventory.documents.edit"))
        self._cancel_button.setEnabled(is_draft and perm.has_permission("inventory.documents.cancel"))
        self._submit_button.setEnabled(is_draft)
        self._post_button.setEnabled(can_post and perm.has_permission("inventory.documents.post"))
        self._reverse_button.setEnabled(can_reverse and perm.has_permission("inventory.documents.post"))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _open_create_dialog(self) -> None:
        if not self._service_registry.permission_service.has_permission("inventory.documents.create"):
            self._show_permission_denied("inventory.documents.create")
            return
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
        if not self._service_registry.permission_service.has_permission("inventory.documents.edit"):
            self._show_permission_denied("inventory.documents.edit")
            return
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
        if not self._service_registry.permission_service.has_permission("inventory.documents.cancel"):
            self._show_permission_denied("inventory.documents.cancel")
            return
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
        reason_code_id = self._select_reason_code("Cancel Draft Document")
        if reason_code_id is None:
            return

        try:
            self._service_registry.inventory_document_service.cancel_draft_document(
                active_company.company_id,
                selected.id,
                CancelInventoryDocumentCommand(
                    reason_code_id=reason_code_id,
                    cancelled_by_user_id=self._service_registry.app_context.current_user_id,
                ),
            )
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "Inventory Documents", str(exc))
            self.reload_documents(selected_document_id=selected.id)
            return
        self.reload_documents()

    def _submit_selected_document(self) -> None:
        active_company = self._active_company()
        selected = self._selected_document()
        if active_company is None or selected is None:
            return
        try:
            result = self._service_registry.inventory_document_service.submit_for_posting(
                active_company.company_id,
                selected.id,
                SubmitInventoryDocumentCommand(
                    submitted_by_user_id=self._service_registry.app_context.current_user_id,
                ),
            )
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "Inventory Documents", str(exc))
            self.reload_documents(selected_document_id=selected.id)
            return
        self.reload_documents(selected_document_id=result.id)

    def _post_selected_document(self) -> None:
        if not self._service_registry.permission_service.has_permission("inventory.documents.post"):
            self._show_permission_denied("inventory.documents.post")
            return
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

    def _reverse_selected_document(self) -> None:
        if not self._service_registry.permission_service.has_permission("inventory.documents.post"):
            self._show_permission_denied("inventory.documents.post")
            return
        active_company = self._active_company()
        selected = self._selected_document()
        if active_company is None or selected is None:
            return
        reason_code_id = self._select_reason_code("Reverse Inventory Document")
        if reason_code_id is None:
            return
        choice = QMessageBox.question(
            self,
            "Reverse Document",
            f"Reverse posted document {selected.document_number}?",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        try:
            result = self._service_registry.inventory_posting_service.reverse_inventory_document(
                active_company.company_id,
                selected.id,
                ReverseInventoryDocumentCommand(
                    reason_code_id=reason_code_id,
                    reverse_date=date.today(),
                    reversed_by_user_id=self._service_registry.app_context.current_user_id,
                ),
            )
        except (ValidationError, NotFoundError, PeriodLockedError) as exc:
            show_error(self, "Inventory Documents", str(exc))
            self.reload_documents(selected_document_id=selected.id)
            return
        show_info(
            self,
            "Inventory Documents",
            f"Document reversed successfully. Reversal document: {result.reversal_document_number}",
        )
        self.reload_documents(selected_document_id=result.reversal_document_id)

    def _select_reason_code(self, title: str) -> int | None:
        active_company = self._active_company()
        if active_company is None:
            return None
        try:
            reasons = self._service_registry.inventory_reference_data_service.list_reason_codes(
                active_company.company_id,
                active_only=True,
            )
        except Exception as exc:
            show_error(self, title, f"Reason codes could not be loaded.\n\n{exc}")
            return None
        if not reasons:
            show_error(self, title, "Create an active inventory reason code before continuing.")
            return None

        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setModal(True)
        form = QFormLayout(dialog)
        form.setContentsMargins(18, 16, 18, 16)
        form.setSpacing(10)
        combo = QComboBox(dialog)
        for reason in reasons:
            combo.addItem(f"{reason.code} — {reason.name}", reason.id)
        form.addRow("Reason", combo)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        value = combo.currentData()
        return int(value) if value is not None else None

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
