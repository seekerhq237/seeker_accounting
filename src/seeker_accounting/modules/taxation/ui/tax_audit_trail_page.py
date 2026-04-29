"""Tax Audit Trail workspace.

Read-only chronological view of taxation-module audit events
(Slice T23). Always scoped to ``module_code = "taxation"``.

Architecture: UI surface only — every read goes through
``TaxAuditTrailService`` via the service registry. The page never
opens its own session or constructs any persistence.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import TYPE_CHECKING

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.shell.ribbon import RibbonHostMixin
from seeker_accounting.modules.taxation.dto.tax_compliance_dto import (
    TaxAuditFilterDTO,
)
from seeker_accounting.platform.exceptions import (
    PermissionDeniedError,
    ValidationError,
)
from seeker_accounting.shared.ui.message_boxes import show_error
from seeker_accounting.shared.ui.table_helpers import configure_compact_table

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.dto.audit_event_dto import AuditEventDTO


_COLUMNS = (
    "Timestamp",
    "Event Type",
    "Entity Type",
    "Entity ID",
    "Description",
    "Actor",
)
_PAGE_SIZE = 200


class TaxAuditTrailPage(RibbonHostMixin, QWidget):
    """Filterable list of taxation-module audit events."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._events: list[AuditEventDTO] = []
        self._offset = 0
        self.setObjectName("TaxAuditTrailPage")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_action_bar())

        self._stack = QStackedWidget(self)
        self._no_company_card = self._build_no_company_card()
        self._workspace = self._build_workspace()
        self._stack.addWidget(self._no_company_card)
        self._stack.addWidget(self._workspace)
        root.addWidget(self._stack, 1)

        self._service_registry.active_company_context.active_company_changed.connect(
            lambda *_: self.reload()
        )
        self.reload()

    # ── Action bar ────────────────────────────────────────────────────

    def _build_action_bar(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageToolbar")

        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)

        title = QLabel("Tax Audit Trail", card)
        title.setObjectName("ToolbarTitle")
        layout.addWidget(title)

        self._meta_label = QLabel(card)
        self._meta_label.setObjectName("ToolbarMeta")
        layout.addWidget(self._meta_label)

        self._event_type_edit = QLineEdit(card)
        self._event_type_edit.setPlaceholderText("Event type filter (e.g. TAX_RETURN_FILED)")
        self._event_type_edit.setFixedWidth(260)
        layout.addWidget(self._event_type_edit)

        layout.addWidget(QLabel("From:", card))
        self._from_date = QDateEdit(card)
        self._from_date.setCalendarPopup(True)
        self._from_date.setDisplayFormat("yyyy-MM-dd")
        self._from_date.setDate(QDate(date.today().year, 1, 1))
        self._from_date.setFixedWidth(120)
        layout.addWidget(self._from_date)

        layout.addWidget(QLabel("To:", card))
        self._to_date = QDateEdit(card)
        self._to_date.setCalendarPopup(True)
        self._to_date.setDisplayFormat("yyyy-MM-dd")
        self._to_date.setDate(QDate(date.today().year, date.today().month, date.today().day))
        self._to_date.setFixedWidth(120)
        layout.addWidget(self._to_date)

        layout.addStretch(1)

        self._apply_button = QPushButton("Apply Filter", card)
        self._apply_button.setProperty("variant", "secondary")
        self._apply_button.clicked.connect(self._reset_and_reload)
        layout.addWidget(self._apply_button)

        self._refresh_button = QPushButton("Refresh", card)
        self._refresh_button.setProperty("variant", "ghost")
        self._refresh_button.clicked.connect(self.reload)
        layout.addWidget(self._refresh_button)

        return card

    # ── No-company state ──────────────────────────────────────────────

    def _build_no_company_card(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)

        title = QLabel("No active company", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)

        body = QLabel(
            "Select a company from the top context bar to view the tax "
            "audit trail.",
            card,
        )
        body.setWordWrap(True)
        layout.addWidget(body)
        layout.addStretch(1)

        return card

    # ── Workspace ─────────────────────────────────────────────────────

    def _build_workspace(self) -> QWidget:
        wrapper = QFrame(self)
        wrapper.setObjectName("PageCard")

        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._table = QTableWidget(wrapper)
        self._table.setObjectName("TaxAuditTrailTable")
        self._table.setColumnCount(len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(list(_COLUMNS))
        configure_compact_table(self._table)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table, 1)

        pager = QFrame(wrapper)
        pager.setObjectName("PageToolbar")
        pager_layout = QHBoxLayout(pager)
        pager_layout.setContentsMargins(8, 4, 8, 4)
        pager_layout.setSpacing(8)

        self._prev_button = QPushButton("\u2190 Previous", pager)
        self._prev_button.setProperty("variant", "ghost")
        self._prev_button.clicked.connect(self._go_previous_page)
        pager_layout.addWidget(self._prev_button)

        self._page_label = QLabel(pager)
        self._page_label.setObjectName("ToolbarMeta")
        pager_layout.addWidget(self._page_label)

        pager_layout.addStretch(1)

        self._next_button = QPushButton("Next \u2192", pager)
        self._next_button.setProperty("variant", "ghost")
        self._next_button.clicked.connect(self._go_next_page)
        pager_layout.addWidget(self._next_button)

        layout.addWidget(pager)

        return wrapper

    # ── Reload / pagination ───────────────────────────────────────────

    def _reset_and_reload(self) -> None:
        self._offset = 0
        self.reload()

    def reload(self) -> None:
        active = self._active_company()
        if active is None:
            self._events = []
            self._meta_label.setText("Select a company")
            self._stack.setCurrentWidget(self._no_company_card)
            return

        from_qd = self._from_date.date()
        to_qd = self._to_date.date()
        from_dt = datetime.combine(date(from_qd.year(), from_qd.month(), from_qd.day()), time.min)
        to_dt = datetime.combine(date(to_qd.year(), to_qd.month(), to_qd.day()), time.max)

        event_type = self._event_type_edit.text().strip() or None

        flt = TaxAuditFilterDTO(
            company_id=active.company_id,
            event_type_code=event_type,
            from_date=from_dt,
            to_date=to_dt,
            limit=_PAGE_SIZE,
            offset=self._offset,
        )
        try:
            self._events = list(
                self._service_registry.tax_audit_trail_service.list_events(flt)
            )
        except PermissionDeniedError as exc:
            self._events = []
            show_error(self, "Tax Audit Trail", str(exc))
        except ValidationError as exc:
            self._events = []
            show_error(self, "Tax Audit Trail", str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            self._events = []
            show_error(self, "Tax Audit Trail", f"Could not load events.\n\n{exc}")

        self._meta_label.setText(f"{len(self._events)} event(s) on this page")
        self._populate_table()
        self._update_pager()
        self._stack.setCurrentWidget(self._workspace)

    def _populate_table(self) -> None:
        self._table.setRowCount(len(self._events))
        for ri, ev in enumerate(self._events):
            self._table.setItem(ri, 0, QTableWidgetItem(ev.created_at.strftime("%Y-%m-%d %H:%M:%S")))
            self._table.setItem(ri, 1, QTableWidgetItem(ev.event_type_code))
            self._table.setItem(ri, 2, QTableWidgetItem(ev.entity_type))
            self._table.setItem(ri, 3, QTableWidgetItem(str(ev.entity_id) if ev.entity_id is not None else ""))
            self._table.setItem(ri, 4, QTableWidgetItem(ev.description))
            self._table.setItem(ri, 5, QTableWidgetItem(ev.actor_display_name or ""))

    def _update_pager(self) -> None:
        page = (self._offset // _PAGE_SIZE) + 1
        self._page_label.setText(f"Page {page}")
        self._prev_button.setEnabled(self._offset > 0)
        # We don't know the total count without an extra query; allow next
        # whenever the page is full.
        self._next_button.setEnabled(len(self._events) >= _PAGE_SIZE)

    def _go_previous_page(self) -> None:
        self._offset = max(0, self._offset - _PAGE_SIZE)
        self.reload()

    def _go_next_page(self) -> None:
        self._offset += _PAGE_SIZE
        self.reload()

    # ── IRibbonHost ───────────────────────────────────────────────────

    def _ribbon_commands(self) -> dict:
        return {
            "tax_audit_trail.refresh": self.reload,
            "tax_audit_trail.apply_filter": self._reset_and_reload,
        }

    def ribbon_state(self) -> dict:
        return {
            "tax_audit_trail.refresh": True,
            "tax_audit_trail.apply_filter": True,
        }

    # ── Helpers ───────────────────────────────────────────────────────

    def _active_company(self):
        return self._service_registry.company_context_service.get_active_company()
