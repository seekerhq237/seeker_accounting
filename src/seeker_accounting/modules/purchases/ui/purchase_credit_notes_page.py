from __future__ import annotations

import logging
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
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
from seeker_accounting.modules.purchases.dto.purchase_credit_note_dto import PurchaseCreditNoteListItemDTO
from seeker_accounting.modules.purchases.ui.purchase_credit_note_dialog import PurchaseCreditNoteDialog
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, PermissionDeniedError, ValidationError
from seeker_accounting.shared.ui.components import (
    DataTable,
    DataTableColumn,
    apply_status_chip_to_column,
)
from seeker_accounting.shared.ui.message_boxes import show_error, show_info

_STATUS_LABELS: dict[str, str] = {
    "draft": "Draft",
    "posted": "Posted",
    "cancelled": "Cancelled",
}

_COL_NUMBER = 0
_COL_SUPPLIER = 1
_COL_DATE = 2
_COL_STATUS = 3
_COL_SOURCE_BILL = 4
_COL_TOTAL = 5

_CREDIT_NOTE_COLUMNS: tuple[DataTableColumn, ...] = (
    DataTableColumn(key="credit_number", title="Credit #"),
    DataTableColumn(key="supplier_name", title="Supplier"),
    DataTableColumn(key="credit_date", title="Date"),
    DataTableColumn(key="status", title="Status"),
    DataTableColumn(key="source_bill_number", title="Source Bill"),
    DataTableColumn(key="total_amount", title="Total", is_numeric=True),
)


_log = logging.getLogger(__name__)


class PurchaseCreditNotesPage(QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._notes: list[PurchaseCreditNoteListItemDTO] = []

        self.setObjectName("PurchaseCreditNotesPage")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)
        root.addWidget(self._build_action_bar())
        root.addWidget(self._build_content_stack(), 1)

        self._service_registry.active_company_context.active_company_changed.connect(
            self._handle_active_company_changed
        )
        self.reload()

    # ------------------------------------------------------------------
    # Reload
    # ------------------------------------------------------------------

    def reload(self, selected_id: int | None = None) -> None:
        active = self._active_company()
        if active is None:
            self._notes = []
            self._notes_model.removeRows(0, self._notes_model.rowCount())
            self._record_count_label.setText("Select a company")
            self._stack.setCurrentWidget(self._no_company_state)
            self._update_action_state()
            return

        try:
            self._notes = self._service_registry.purchase_credit_note_service.list_credit_notes(
                active.company_id,
                status_code=self._status_filter_value(),
            )
        except Exception as exc:
            self._notes = []
            self._notes_model.removeRows(0, self._notes_model.rowCount())
            self._record_count_label.setText("Unable to load")
            self._stack.setCurrentWidget(self._empty_state)
            self._update_action_state()
            show_error(self, "Purchase Credit Notes", f"Could not load credit notes.\n\n{exc}")
            return

        self._populate_table()
        self._update_record_count_label()
        self._sync_surface(active)
        self._restore_selection(selected_id)
        self._update_action_state()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_action_bar(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageToolbar")
        card.setProperty("card", True)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)
        self._search_input = QLineEdit(card)
        self._search_input.setPlaceholderText("Search credit notes...")
        self._search_input.setFixedWidth(180)
        layout.addWidget(self._search_input)

        self._status_filter = QComboBox(card)
        self._status_filter.addItem("All statuses", None)
        self._status_filter.addItem("Draft", "draft")
        self._status_filter.addItem("Posted", "posted")
        self._status_filter.addItem("Cancelled", "cancelled")
        self._status_filter.currentIndexChanged.connect(lambda _: self.reload())
        layout.addWidget(self._status_filter)

        layout.addStretch(1)

        self._new_btn = QPushButton("New Credit Note", card)
        self._new_btn.setProperty("variant", "primary")
        self._new_btn.clicked.connect(self._handle_new)
        layout.addWidget(self._new_btn)

        self._edit_btn = QPushButton("Edit Draft", card)
        self._edit_btn.setProperty("variant", "secondary")
        self._edit_btn.clicked.connect(self._handle_edit)
        layout.addWidget(self._edit_btn)

        self._post_btn = QPushButton("Post", card)
        self._post_btn.setProperty("variant", "secondary")
        self._post_btn.clicked.connect(self._handle_post)
        layout.addWidget(self._post_btn)

        self._cancel_btn = QPushButton("Cancel", card)
        self._cancel_btn.setProperty("variant", "ghost")
        self._cancel_btn.clicked.connect(self._handle_cancel)
        layout.addWidget(self._cancel_btn)

        self._refresh_btn = QPushButton("Refresh", card)
        self._refresh_btn.setProperty("variant", "ghost")
        self._refresh_btn.clicked.connect(lambda: self.reload())
        layout.addWidget(self._refresh_btn)

        return card

    def _build_content_stack(self) -> QStackedWidget:
        self._stack = QStackedWidget(self)

        self._no_company_state = QFrame(self._stack)
        nc_layout = QVBoxLayout(self._no_company_state)
        nc_label = QLabel("Select an active company to view purchase credit notes.", self._no_company_state)
        nc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nc_label.setObjectName("EmptyStateLabel")
        nc_layout.addWidget(nc_label)
        self._stack.addWidget(self._no_company_state)

        card = QFrame(self._stack)
        card.setObjectName("PageCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        sub_header = QWidget(card)
        sh_layout = QHBoxLayout(sub_header)
        sh_layout.setContentsMargins(16, 10, 16, 10)
        self._record_count_label = QLabel("", sub_header)
        self._record_count_label.setObjectName("RecordCountLabel")
        sh_layout.addWidget(self._record_count_label)
        sh_layout.addStretch(1)
        card_layout.addWidget(sub_header)

        self._notes_model = QStandardItemModel(0, len(_CREDIT_NOTE_COLUMNS), card)
        self._notes_model.setHorizontalHeaderLabels([c.title for c in _CREDIT_NOTE_COLUMNS])

        self._table = DataTable(
            columns=_CREDIT_NOTE_COLUMNS,
            show_search=False,
            show_count=False,
            show_density_toggle=True,
            show_column_chooser=True,
            selection_mode="single",
            empty_state_text="No credit notes match the current filters.",
            parent=card,
        )
        self._table.set_model(self._notes_model)
        self._notes_status_delegate = apply_status_chip_to_column(
            self._table.view(), _COL_STATUS
        )
        self._table.selection_changed.connect(self._on_selection_changed)
        self._table.row_activated.connect(self._on_row_activated)
        self._search_input.textChanged.connect(self._table.set_search_text)
        self._search_input.textChanged.connect(self._update_record_count_label)
        card_layout.addWidget(self._table, 1)
        self._stack.addWidget(card)
        self._stack.setCurrentWidget(card)

        self._empty_state = QFrame(self._stack)
        es_layout = QVBoxLayout(self._empty_state)
        es_label = QLabel("No credit notes found.", self._empty_state)
        es_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        es_label.setObjectName("EmptyStateLabel")
        es_layout.addWidget(es_label)
        self._stack.addWidget(self._empty_state)

        return self._stack

    # ------------------------------------------------------------------
    # Table population
    # ------------------------------------------------------------------

    @staticmethod
    def _make_item(text: str, *, user_data: object | None = None) -> QStandardItem:
        item = QStandardItem(text or "")
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
        self._notes_model.removeRows(0, self._notes_model.rowCount())
        for note in self._notes:
            items = [
                self._make_item(note.credit_number, user_data=note.id),
                self._make_item(note.supplier_name),
                self._make_item(note.credit_date.isoformat()),
                self._make_item(note.status_code),
                self._make_item(note.source_bill_number or ""),
                self._make_numeric(note.total_amount),
            ]
            self._notes_model.appendRow(items)

    def _update_record_count_label(self, *_args: object) -> None:
        total = len(self._notes)
        query = self._search_input.text().strip()
        if query:
            proxy = self._table.view().model()
            visible = proxy.rowCount() if proxy is not None else total
            self._record_count_label.setText(
                f"{visible} shown of {total} credit note(s)"
            )
        else:
            self._record_count_label.setText(f"{total} credit note(s)")

    def _sync_surface(self, active) -> None:
        has_rows = bool(self._notes)
        self._stack.setCurrentWidget(
            self._empty_state if not has_rows else self._stack.widget(1)
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _handle_new(self) -> None:
        if not self._service_registry.permission_service.has_permission("purchases.credit_notes.create"):
            self._show_permission_denied("purchases.credit_notes.create")
            return
        active = self._active_company()
        if active is None:
            show_error(self, "Credit Notes", "No active company selected.")
            return
        result = PurchaseCreditNoteDialog.create_credit_note(
            self._service_registry, active.company_id, active.display_name, parent=self
        )
        if result is not None:
            self.reload(selected_id=result.id)

    def _handle_edit(self) -> None:
        if not self._service_registry.permission_service.has_permission("purchases.credit_notes.edit"):
            self._show_permission_denied("purchases.credit_notes.edit")
            return
        note_id = self._selected_note_id()
        if note_id is None:
            return
        note = next((n for n in self._notes if n.id == note_id), None)
        if note is None:
            return
        if note.status_code != "draft":
            show_error(self, "Edit Credit Note", "Only draft credit notes can be edited.")
            return
        active = self._active_company()
        if active is None:
            return
        result = PurchaseCreditNoteDialog.edit_credit_note(
            self._service_registry, active.company_id, active.display_name, note_id, parent=self
        )
        if result is not None:
            self.reload(selected_id=result.id)

    def _handle_post(self) -> None:
        if not self._service_registry.permission_service.has_permission("purchases.credit_notes.post"):
            self._show_permission_denied("purchases.credit_notes.post")
            return
        note_id = self._selected_note_id()
        if note_id is None:
            return
        note = next((n for n in self._notes if n.id == note_id), None)
        if note is None:
            return
        if note.status_code != "draft":
            show_error(self, "Post Credit Note", "Only draft credit notes can be posted.")
            return
        active = self._active_company()
        if active is None:
            return
        reply = QMessageBox.question(
            self,
            "Post Credit Note",
            f"Post credit note {note.credit_number}?\n\nThis will create a journal entry and the credit note will become immutable.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            result = self._service_registry.purchase_credit_note_posting_service.post_credit_note(
                active.company_id, note_id
            )
            show_info(self, "Post Credit Note", f"Credit note {result.credit_number} posted successfully.")
            self.reload(selected_id=note_id)
        except (ValidationError, NotFoundError, ConflictError) as exc:
            show_error(self, "Post Credit Note", str(exc))
        except AppError as exc:
            show_error(self, "Post Credit Note", f"Unexpected error: {exc}")

        except Exception:
            _log.exception("Post Credit Note")
            show_error(self, "Post Credit Note", "An unexpected error occurred. See application log for details.")

    def _handle_cancel(self) -> None:
        if not self._service_registry.permission_service.has_permission("purchases.credit_notes.cancel"):
            self._show_permission_denied("purchases.credit_notes.cancel")
            return
        note_id = self._selected_note_id()
        if note_id is None:
            return
        note = next((n for n in self._notes if n.id == note_id), None)
        if note is None or note.status_code == "cancelled":
            return
        if note.status_code == "posted":
            show_error(self, "Cancel Credit Note", "Posted credit notes cannot be cancelled.")
            return
        reply = QMessageBox.question(
            self,
            "Cancel Credit Note",
            f"Cancel credit note {note.credit_number}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        active = self._active_company()
        if active is None:
            return
        try:
            self._service_registry.purchase_credit_note_service.cancel_credit_note(active.company_id, note_id)
            self.reload()
        except (ValidationError, NotFoundError, ConflictError) as exc:
            show_error(self, "Cancel Credit Note", str(exc))
        except AppError as exc:
            show_error(self, "Cancel Credit Note", f"Unexpected error: {exc}")

        except Exception:
            _log.exception("Cancel Credit Note")
            show_error(self, "Cancel Credit Note", "An unexpected error occurred. See application log for details.")

    def _handle_double_click(self) -> None:
        note_id = self._selected_note_id()
        if note_id is None:
            return
        note = next((n for n in self._notes if n.id == note_id), None)
        if note and note.status_code == "draft":
            self._handle_edit()

    def _on_selection_changed(self, _rows: list[int]) -> None:
        self._update_action_state()

    def _on_row_activated(self, _row: int) -> None:
        self._handle_double_click()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _update_action_state(self) -> None:
        note_id = self._selected_note_id()
        note = next((n for n in self._notes if n.id == note_id), None) if note_id else None
        active = self._active_company()
        perm = self._service_registry.permission_service
        has_company = active is not None
        is_draft = note is not None and note.status_code == "draft"
        self._new_btn.setEnabled(has_company and perm.has_permission("purchases.credit_notes.create"))
        self._edit_btn.setEnabled(is_draft and perm.has_permission("purchases.credit_notes.edit"))
        self._post_btn.setEnabled(is_draft and perm.has_permission("purchases.credit_notes.post"))
        self._cancel_btn.setEnabled(is_draft and perm.has_permission("purchases.credit_notes.cancel"))

    def _selected_note_id(self) -> int | None:
        rows = self._table.selected_rows()
        if not rows:
            return None
        idx = rows[0]
        if 0 <= idx < len(self._notes):
            return self._notes[idx].id
        return None

    def _active_company(self):
        return self._service_registry.company_context_service.get_active_company()

    def _show_permission_denied(self, permission_code: str) -> None:
        show_error(
            self,
            "Permission Denied",
            self._service_registry.permission_service.build_denied_message(permission_code),
        )

    def _status_filter_value(self) -> str | None:
        return self._status_filter.currentData()

    def _restore_selection(self, selected_id: int | None) -> None:
        if not self._notes:
            return
        if selected_id is None:
            target_idx = 0
        else:
            target_idx = next(
                (i for i, n in enumerate(self._notes) if n.id == selected_id),
                0,
            )
        proxy = self._table.view().model()
        if proxy is None:
            return
        src_index = self._notes_model.index(target_idx, 0)
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

    def _handle_active_company_changed(self) -> None:
        self.reload()
