"""Audit Log viewer — read-only page for browsing all audit events."""
from __future__ import annotations

import logging

from datetime import date, datetime
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.shared.ui.components import (
    DataTable,
    DataTableColumn,
)
from seeker_accounting.shared.ui.message_boxes import show_error

if TYPE_CHECKING:
    from seeker_accounting.app.dependency.service_registry import ServiceRegistry
    from seeker_accounting.modules.audit.dto.audit_event_dto import AuditEventDTO

_log = logging.getLogger(__name__)


AUDIT_COLUMNS: tuple[DataTableColumn, ...] = (
    DataTableColumn(key="timestamp", title="Timestamp"),
    DataTableColumn(key="event_type", title="Event Type"),
    DataTableColumn(key="module", title="Module"),
    DataTableColumn(key="entity_type", title="Entity Type"),
    DataTableColumn(key="entity_id", title="Entity ID"),
    DataTableColumn(key="description", title="Description"),
    DataTableColumn(key="actor", title="Actor"),
)

_PAGE_SIZE = 200


class AuditLogPage(QWidget):
    """Global audit log viewer with server-side filtering and pagination."""

    def __init__(
        self,
        service_registry: "ServiceRegistry",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._events: list[AuditEventDTO] = []
        self._offset = 0
        self.setObjectName("AuditLogPage")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_action_bar())
        root_layout.addWidget(self._build_content_stack(), 1)

        self._service_registry.active_company_context.active_company_changed.connect(
            self._handle_company_changed
        )
        self._search_edit.textChanged.connect(self._table.set_search_text)
        self._search_edit.textChanged.connect(self._update_record_count_label)

        self.reload_audit_events()

    # ── Action bar ────────────────────────────────────────────────────

    def _build_action_bar(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageToolbar")
        card.setProperty("card", True)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)

        title = QLabel("Audit Log", card)
        title.setObjectName("ToolbarTitle")
        layout.addWidget(title)

        self._record_count_label = QLabel(card)
        self._record_count_label.setObjectName("ToolbarMeta")
        layout.addWidget(self._record_count_label)

        self._search_edit = QLineEdit(card)
        self._search_edit.setPlaceholderText("Search description, event type, or actor")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.setFixedWidth(240)
        layout.addWidget(self._search_edit)

        # Module filter
        mod_label = QLabel("Module:", card)
        layout.addWidget(mod_label)
        self._module_combo = QComboBox(card)
        self._module_combo.setFixedWidth(160)
        self._module_combo.addItem("All Modules", "")
        self._module_combo.currentIndexChanged.connect(lambda _: self.reload_audit_events())
        layout.addWidget(self._module_combo)

        # Date range filters
        from_label = QLabel("From:", card)
        layout.addWidget(from_label)
        self._from_date = QDateEdit(card)
        self._from_date.setCalendarPopup(True)
        self._from_date.setDate(date.today().replace(day=1))
        self._from_date.setDisplayFormat("yyyy-MM-dd")
        self._from_date.setFixedWidth(130)
        layout.addWidget(self._from_date)

        to_label = QLabel("To:", card)
        layout.addWidget(to_label)
        self._to_date = QDateEdit(card)
        self._to_date.setCalendarPopup(True)
        self._to_date.setDate(date.today())
        self._to_date.setDisplayFormat("yyyy-MM-dd")
        self._to_date.setFixedWidth(130)
        layout.addWidget(self._to_date)

        layout.addStretch(1)

        self._apply_filter_button = QPushButton("Apply Filter", card)
        self._apply_filter_button.setProperty("variant", "secondary")
        self._apply_filter_button.clicked.connect(lambda: self.reload_audit_events())
        layout.addWidget(self._apply_filter_button)

        self._refresh_button = QPushButton("Refresh", card)
        self._refresh_button.setProperty("variant", "ghost")
        self._refresh_button.clicked.connect(lambda: self.reload_audit_events())
        layout.addWidget(self._refresh_button)

        return card

    # ── Content stack ─────────────────────────────────────────────────

    def _build_content_stack(self) -> QWidget:
        self._stack = QStackedWidget(self)
        self._table_surface = self._build_table_surface()
        self._empty_state = self._build_empty_state()
        self._no_company_state = self._build_no_company_state()
        self._stack.addWidget(self._table_surface)
        self._stack.addWidget(self._empty_state)
        self._stack.addWidget(self._no_company_state)
        return self._stack

    def _build_table_surface(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._audit_log_model = QStandardItemModel(0, len(AUDIT_COLUMNS), self)
        self._audit_log_model.setHorizontalHeaderLabels([c.title for c in AUDIT_COLUMNS])

        self._table = DataTable(
            columns=AUDIT_COLUMNS,
            show_search=False,
            show_count=False,
            show_density_toggle=True,
            show_column_chooser=True,
            selection_mode="single",
            empty_state_text="No audit events match the current filters.",
            parent=card,
        )
        self._table.set_model(self._audit_log_model)
        layout.addWidget(self._table)

        # ── Pagination ──
        pager = QWidget(card)
        pager_layout = QHBoxLayout(pager)
        pager_layout.setContentsMargins(0, 4, 0, 0)
        pager_layout.setSpacing(10)

        self._prev_button = QPushButton("← Previous", pager)
        self._prev_button.setProperty("variant", "ghost")
        self._prev_button.clicked.connect(self._go_previous_page)
        pager_layout.addWidget(self._prev_button)

        self._page_label = QLabel(pager)
        self._page_label.setObjectName("ToolbarMeta")
        pager_layout.addWidget(self._page_label)

        self._next_button = QPushButton("Next →", pager)
        self._next_button.setProperty("variant", "ghost")
        self._next_button.clicked.connect(self._go_next_page)
        pager_layout.addWidget(self._next_button)

        pager_layout.addStretch(1)
        layout.addWidget(pager)

        return card

    def _build_empty_state(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)

        title = QLabel("No audit events found", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)

        summary = QLabel(
            "No audit events match the current filters. "
            "Adjust the date range or module filter to see results.",
            card,
        )
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        layout.addStretch(1)
        return card

    def _build_no_company_state(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)

        title = QLabel("No active company", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)

        summary = QLabel(
            "Select a company from the top bar to view its audit log.",
            card,
        )
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        layout.addStretch(1)
        return card

    # ── Data loading ──────────────────────────────────────────────────

    def reload_audit_events(self) -> None:
        company_id = self._service_registry.active_company_context.company_id
        if company_id is None:
            self._events = []
            self._stack.setCurrentWidget(self._no_company_state)
            return

        audit_service = self._service_registry.audit_service

        # Gather filter values
        module_code = self._module_combo.currentData() or None
        from_dt = datetime.combine(self._from_date.date().toPython(), datetime.min.time())
        to_dt = datetime.combine(self._to_date.date().toPython(), datetime.max.time())

        try:
            self._events = audit_service.list_events(
                company_id=company_id,
                module_code=module_code,
                from_date=from_dt,
                to_date=to_dt,
                limit=_PAGE_SIZE,
                offset=self._offset,
            )
        except AppError as exc:
            show_error(self, "Audit Log", f"Failed to load audit events: {exc}")

        except Exception:
            _log.exception("Audit Log")
            show_error(self, "Audit Log", "An unexpected error occurred. See application log for details.")
            self._events = []

        # Populate the module combo if not yet done
        if self._module_combo.count() <= 1:
            self._populate_module_combo(company_id)

        if self._events:
            self._populate_table()
            self._stack.setCurrentWidget(self._table_surface)
        else:
            self._stack.setCurrentWidget(self._empty_state)

        self._update_pagination()

    def _populate_module_combo(self, company_id: int) -> None:
        try:
            codes = self._service_registry.audit_service.distinct_module_codes(company_id)
        except Exception:
            _log.warning("Form data load error", exc_info=True)
            return
        self._module_combo.blockSignals(True)
        current = self._module_combo.currentData()
        self._module_combo.clear()
        self._module_combo.addItem("All Modules", "")
        for code in sorted(codes):
            self._module_combo.addItem(code.replace("_", " ").title(), code)
        # Restore selection
        if current:
            idx = self._module_combo.findData(current)
            if idx >= 0:
                self._module_combo.setCurrentIndex(idx)
        self._module_combo.blockSignals(False)

    @staticmethod
    def _make_item(text: str, *, user_data: object | None = None) -> QStandardItem:
        item = QStandardItem(text or "")
        item.setEditable(False)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item

    def _populate_table(self) -> None:
        self._audit_log_model.removeRows(0, self._audit_log_model.rowCount())

        for event in self._events:
            ts_str = event.created_at.strftime("%Y-%m-%d %H:%M:%S") if event.created_at else ""
            actor = event.actor_display_name or (f"User #{event.actor_user_id}" if event.actor_user_id else "System")
            entity_id_str = str(event.entity_id) if event.entity_id else ""

            entity_id_item = self._make_item(entity_id_str)
            entity_id_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            self._audit_log_model.appendRow(
                [
                    self._make_item(ts_str, user_data=event.id),
                    self._make_item(event.event_type_code),
                    self._make_item(event.module_code),
                    self._make_item(event.entity_type),
                    entity_id_item,
                    self._make_item(event.description),
                    self._make_item(actor),
                ]
            )

        self._update_record_count_label()

    # ── Pagination ────────────────────────────────────────────────────

    def _update_pagination(self) -> None:
        page = (self._offset // _PAGE_SIZE) + 1
        self._page_label.setText(f"Page {page}")
        self._prev_button.setEnabled(self._offset > 0)
        self._next_button.setEnabled(len(self._events) == _PAGE_SIZE)

    def _go_previous_page(self) -> None:
        self._offset = max(0, self._offset - _PAGE_SIZE)
        self.reload_audit_events()

    def _go_next_page(self) -> None:
        self._offset += _PAGE_SIZE
        self.reload_audit_events()

    # ── Client-side search ────────────────────────────────────────────

    def _update_record_count_label(self, *_args) -> None:
        total = len(self._events)
        query = self._search_edit.text().strip()
        if query:
            proxy = self._table.view().model()
            visible = proxy.rowCount() if proxy is not None else total
            self._record_count_label.setText(f"{visible} shown of {total} events")
        else:
            self._record_count_label.setText(f"{total} event(s)")

    # ── Signal handlers ───────────────────────────────────────────────

    def _handle_company_changed(self) -> None:
        self._offset = 0
        # Reset module combo
        self._module_combo.blockSignals(True)
        self._module_combo.clear()
        self._module_combo.addItem("All Modules", "")
        self._module_combo.blockSignals(False)
        self.reload_audit_events()
