from __future__ import annotations

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
from seeker_accounting.modules.purchases.dto.purchase_credit_note_dto import PurchaseCreditNoteListItemDTO
from seeker_accounting.modules.purchases.ui.purchase_credit_note_dialog import PurchaseCreditNoteDialog
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.table_helpers import configure_compact_table

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
            self._table.setRowCount(0)
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
            self._table.setRowCount(0)
            self._record_count_label.setText("Unable to load")
            self._stack.setCurrentWidget(self._empty_state)
            self._update_action_state()
            show_error(self, "Purchase Credit Notes", f"Could not load credit notes.\n\n{exc}")
            return

        self._populate_table()
        self._apply_search()
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
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(12)

        self._search_input = QLineEdit(card)
        self._search_input.setPlaceholderText("Search credit notes...")
        self._search_input.setFixedWidth(180)
        self._search_input.textChanged.connect(lambda _: self._apply_search())
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

        self._table = QTableWidget(0, 6, card)
        self._table.setHorizontalHeaderLabels(
            ["Credit #", "Supplier", "Date", "Status", "Source Bill", "Total"]
        )
        configure_compact_table(self._table)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.itemSelectionChanged.connect(self._update_action_state)
        self._table.itemDoubleClicked.connect(self._handle_double_click)
        self._table.horizontalHeader().setStretchLastSection(False)
        hh = self._table.horizontalHeader()
        hh.resizeSection(_COL_NUMBER, 120)
        hh.resizeSection(_COL_SUPPLIER, 180)
        hh.resizeSection(_COL_DATE, 100)
        hh.resizeSection(_COL_STATUS, 90)
        hh.resizeSection(_COL_SOURCE_BILL, 130)
        hh.resizeSection(_COL_TOTAL, 100)
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

    def _populate_table(self) -> None:
        self._table.setRowCount(0)
        for note in self._notes:
            row = self._table.rowCount()
            self._table.insertRow(row)

            num_item = QTableWidgetItem(note.credit_number)
            num_item.setFlags(num_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            num_item.setData(Qt.ItemDataRole.UserRole, note.id)
            self._table.setItem(row, _COL_NUMBER, num_item)

            self._set_item(row, _COL_SUPPLIER, note.supplier_name)
            self._set_item(row, _COL_DATE, note.credit_date.isoformat())
            self._set_status_chip(row, _COL_STATUS, note.status_code)
            self._set_item(row, _COL_SOURCE_BILL, note.source_bill_number or "")

            total_item = QTableWidgetItem(f"{note.total_amount:,.2f}")
            total_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            total_item.setFlags(total_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, _COL_TOTAL, total_item)

    def _set_item(self, row: int, col: int, text: str) -> None:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self._table.setItem(row, col, item)

    def _set_status_chip(self, row: int, col: int, status_code: str) -> None:
        label = _STATUS_LABELS.get(status_code, status_code)
        item = QTableWidgetItem(label)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        if status_code == "posted":
            item.setForeground(Qt.GlobalColor.darkGreen)
        elif status_code == "draft":
            item.setForeground(Qt.GlobalColor.darkGray)
        elif status_code == "cancelled":
            item.setForeground(Qt.GlobalColor.red)
        self._table.setItem(row, col, item)

    def _apply_search(self) -> None:
        term = self._search_input.text().strip().lower()
        for row in range(self._table.rowCount()):
            visible = not term
            if term:
                for col in (_COL_NUMBER, _COL_SUPPLIER, _COL_SOURCE_BILL):
                    item = self._table.item(row, col)
                    if item and term in item.text().lower():
                        visible = True
                        break
            self._table.setRowHidden(row, not visible)
        visible_count = sum(1 for r in range(self._table.rowCount()) if not self._table.isRowHidden(r))
        self._record_count_label.setText(f"{visible_count} credit note(s)")

    def _sync_surface(self, active) -> None:
        has_rows = self._table.rowCount() > 0
        self._stack.setCurrentWidget(
            self._empty_state if not has_rows else self._stack.widget(1)
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _handle_new(self) -> None:
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
        except Exception as exc:
            show_error(self, "Post Credit Note", f"Unexpected error: {exc}")

    def _handle_cancel(self) -> None:
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
        except Exception as exc:
            show_error(self, "Cancel Credit Note", f"Unexpected error: {exc}")

    def _handle_double_click(self) -> None:
        note_id = self._selected_note_id()
        if note_id is None:
            return
        note = next((n for n in self._notes if n.id == note_id), None)
        if note and note.status_code == "draft":
            self._handle_edit()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _update_action_state(self) -> None:
        note_id = self._selected_note_id()
        note = next((n for n in self._notes if n.id == note_id), None) if note_id else None
        active = self._active_company()
        has_company = active is not None
        is_draft = note is not None and note.status_code == "draft"
        self._new_btn.setEnabled(has_company)
        self._edit_btn.setEnabled(is_draft)
        self._post_btn.setEnabled(is_draft)
        self._cancel_btn.setEnabled(is_draft)

    def _selected_note_id(self) -> int | None:
        rows = self._table.selectedItems()
        if not rows:
            return None
        row = self._table.currentRow()
        item = self._table.item(row, _COL_NUMBER)
        if item is None:
            return None
        val = item.data(Qt.ItemDataRole.UserRole)
        return val if isinstance(val, int) else None

    def _active_company(self):
        return self._service_registry.company_context_service.get_active_company()

    def _status_filter_value(self) -> str | None:
        return self._status_filter.currentData()

    def _restore_selection(self, selected_id: int | None) -> None:
        if selected_id is None:
            return
        for row in range(self._table.rowCount()):
            item = self._table.item(row, _COL_NUMBER)
            if item and item.data(Qt.ItemDataRole.UserRole) == selected_id:
                self._table.selectRow(row)
                break

    def _handle_active_company_changed(self) -> None:
        self.reload()
