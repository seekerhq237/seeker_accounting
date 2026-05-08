"""Deferral list page — main workspace for prepaid expenses and unearned revenue."""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.accounting.deferrals.dto.deferral_dto import (
    CancelDeferralScheduleCommand,
    DeferralScheduleDTO,
)
from seeker_accounting.modules.accounting.deferrals.ui.deferral_dialog import DeferralDialog
from seeker_accounting.modules.accounting.deferrals.ui.deferral_lines_dialog import DeferralLinesDialog
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError
from seeker_accounting.shared.ui.message_boxes import show_error, show_info

_DASH = "\u2014"


def _money(v: Decimal | None) -> str:
    if v is None:
        return _DASH
    return f"{v:,.2f}"


def _right(item: QTableWidgetItem) -> QTableWidgetItem:
    item.setTextAlignment(int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
    return item


class DeferralListPage(QWidget):
    """Lists all deferral schedules for the active company."""

    COLUMNS = (
        "Description",
        "Type",
        "Total",
        "Posted",
        "Remaining",
        "Start",
        "Periods",
        "Status",
    )

    def __init__(
        self,
        service_registry: ServiceRegistry,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._schedules: list[DeferralScheduleDTO] = []

        self.setObjectName("DeferralListPage")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_toolbar())

        self._stack = QStackedWidget(self)
        self._no_company = self._build_no_company_card()
        self._workspace = self._build_workspace()
        self._stack.addWidget(self._no_company)
        self._stack.addWidget(self._workspace)
        root.addWidget(self._stack, 1)

        self._service_registry.active_company_context.active_company_changed.connect(
            lambda *_: self.reload()
        )
        self.reload()

    # ── Build ─────────────────────────────────────────────────────────

    def _build_toolbar(self) -> QWidget:
        bar = QFrame(self)
        bar.setObjectName("PageToolbar")

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)

        title = QLabel("Deferrals", bar)
        title.setObjectName("ToolbarTitle")
        layout.addWidget(title)

        self._meta_label = QLabel(bar)
        self._meta_label.setObjectName("ToolbarMeta")
        layout.addWidget(self._meta_label)

        layout.addStretch(1)

        # Filter by type
        self._type_filter = QComboBox(bar)
        self._type_filter.addItem("All types", None)
        self._type_filter.addItem("Prepaid Expense", "EXPENSE")
        self._type_filter.addItem("Unearned Revenue", "REVENUE")
        self._type_filter.currentIndexChanged.connect(self.reload)
        layout.addWidget(self._type_filter)

        # Filter by status
        self._status_filter = QComboBox(bar)
        self._status_filter.addItem("All statuses", None)
        self._status_filter.addItem("Draft", "DRAFT")
        self._status_filter.addItem("Active", "ACTIVE")
        self._status_filter.addItem("Complete", "COMPLETE")
        self._status_filter.addItem("Cancelled", "CANCELLED")
        self._status_filter.currentIndexChanged.connect(self.reload)
        layout.addWidget(self._status_filter)

        new_btn = QPushButton("New Deferral", bar)
        new_btn.setProperty("variant", "primary")
        new_btn.clicked.connect(self._handle_new)
        layout.addWidget(new_btn)

        return bar

    def _build_no_company_card(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("EmptyStateCard")
        layout = QVBoxLayout(card)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg = QLabel("No company selected.", card)
        msg.setObjectName("EmptyStateMessage")
        layout.addWidget(msg)
        return card

    def _build_workspace(self) -> QWidget:
        widget = QWidget(self)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._table = QTableWidget(widget)
        self._table.setColumnCount(len(self.COLUMNS))
        self._table.setHorizontalHeaderLabels(list(self.COLUMNS))
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.doubleClicked.connect(self._handle_open)
        layout.addWidget(self._table, 1)

        # Bottom action bar
        action_bar = QFrame(widget)
        action_bar.setObjectName("BottomActionBar")
        ab_layout = QHBoxLayout(action_bar)
        ab_layout.setContentsMargins(8, 4, 8, 4)
        ab_layout.setSpacing(6)
        ab_layout.addStretch(1)

        open_btn = QPushButton("Open Lines", action_bar)
        open_btn.clicked.connect(self._handle_open)
        ab_layout.addWidget(open_btn)

        cancel_btn = QPushButton("Cancel Schedule", action_bar)
        cancel_btn.clicked.connect(self._handle_cancel)
        ab_layout.addWidget(cancel_btn)

        layout.addWidget(action_bar)
        return widget

    # ── Reload ────────────────────────────────────────────────────────

    def reload(self) -> None:
        company = self._service_registry.company_context_service.get_active_company()
        if company is None:
            self._schedules = []
            self._stack.setCurrentWidget(self._no_company)
            return

        self._stack.setCurrentWidget(self._workspace)
        type_filter: str | None = self._type_filter.currentData()
        status_filter: str | None = self._status_filter.currentData()

        try:
            self._schedules = self._service_registry.deferral_service.list_schedules(
                company.company_id,
                deferral_type=type_filter,
                status_code=status_filter,
            )
        except Exception as exc:
            show_error(self, "Error", f"Could not load deferrals: {exc}")
            self._schedules = []

        self._meta_label.setText(f"{len(self._schedules)} schedule(s)")
        self._populate_table()

    def _populate_table(self) -> None:
        self._table.setRowCount(len(self._schedules))
        for row, s in enumerate(self._schedules):
            type_label = "Prepaid Expense" if s.deferral_type == "EXPENSE" else "Unearned Revenue"
            self._table.setItem(row, 0, QTableWidgetItem(s.description))
            self._table.setItem(row, 1, QTableWidgetItem(type_label))
            self._table.setItem(row, 2, _right(QTableWidgetItem(_money(s.total_amount))))
            self._table.setItem(row, 3, _right(QTableWidgetItem(_money(s.posted_amount))))
            self._table.setItem(row, 4, _right(QTableWidgetItem(_money(s.remaining_amount))))
            self._table.setItem(row, 5, QTableWidgetItem(s.start_date.isoformat()))
            self._table.setItem(row, 6, QTableWidgetItem(str(s.period_count)))
            status_item = QTableWidgetItem(s.status_code)
            if s.status_code == "COMPLETE":
                status_item.setForeground(Qt.GlobalColor.darkGreen)
            elif s.status_code == "CANCELLED":
                status_item.setForeground(Qt.GlobalColor.gray)
            elif s.status_code == "ACTIVE":
                status_item.setForeground(Qt.GlobalColor.darkBlue)
            self._table.setItem(row, 7, status_item)

    # ── Handlers ──────────────────────────────────────────────────────

    def _active_company_id(self) -> int | None:
        co = self._service_registry.company_context_service.get_active_company()
        return co.company_id if co else None

    def _selected_schedule(self) -> DeferralScheduleDTO | None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        row = rows[0].row()
        if row < 0 or row >= len(self._schedules):
            return None
        return self._schedules[row]

    def _handle_new(self) -> None:
        company_id = self._active_company_id()
        if company_id is None:
            return
        dlg = DeferralDialog(self._service_registry, company_id, self)
        if dlg.exec() == DeferralDialog.DialogCode.Accepted:
            self.reload()

    def _handle_open(self) -> None:
        schedule = self._selected_schedule()
        if schedule is None:
            return
        dlg = DeferralLinesDialog(self._service_registry, schedule, self)
        dlg.exec()
        self.reload()

    def _handle_cancel(self) -> None:
        schedule = self._selected_schedule()
        if schedule is None:
            show_error(self, "No selection", "Please select a schedule to cancel.")
            return
        if schedule.status_code in ("COMPLETE", "CANCELLED"):
            show_error(self, "Cannot cancel", f"A {schedule.status_code} schedule cannot be cancelled.")
            return

        company_id = self._active_company_id()
        if company_id is None:
            return

        try:
            self._service_registry.deferral_service.cancel_schedule(
                CancelDeferralScheduleCommand(
                    company_id=company_id,
                    schedule_id=schedule.id,
                )
            )
            show_info(self, "Cancelled", f"Schedule '{schedule.description}' has been cancelled.")
            self.reload()
        except (ValidationError, ConflictError) as exc:
            show_error(self, "Error", str(exc))
        except Exception as exc:
            show_error(self, "Error", f"Could not cancel schedule: {exc}")
