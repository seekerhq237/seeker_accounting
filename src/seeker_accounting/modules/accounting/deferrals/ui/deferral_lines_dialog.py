"""Deferral lines dialog — view and post recognition instalments."""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.accounting.deferrals.dto.deferral_dto import (
    DeferralLineDTO,
    DeferralScheduleDTO,
    PostRecognitionLineCommand,
)
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


class DeferralLinesDialog(QDialog):
    """Show the recognition lines for a deferral schedule and allow posting."""

    COLUMNS = ("Period", "Date", "Amount", "Status", "Journal Entry")

    def __init__(
        self,
        service_registry: ServiceRegistry,
        schedule_dto: DeferralScheduleDTO,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._schedule = schedule_dto

        title = f"Deferral Lines — {schedule_dto.description}"
        self.setWindowTitle(title)
        self.setMinimumWidth(640)
        self.setMinimumHeight(440)
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setSpacing(8)

        # Summary bar
        summary = QHBoxLayout()
        self._summary_label = QLabel(self)
        self._summary_label.setObjectName("DetailSectionHeader")
        summary.addWidget(self._summary_label)
        summary.addStretch()
        if schedule_dto.status_code == "DRAFT":
            activate_btn = QPushButton("Activate Schedule", self)
            activate_btn.setProperty("variant", "primary")
            activate_btn.clicked.connect(self._handle_activate)
            summary.addWidget(activate_btn)
        root.addLayout(summary)

        # Period selector for posting
        if schedule_dto.status_code == "ACTIVE":
            period_bar = QHBoxLayout()
            period_bar.addWidget(QLabel("Post to fiscal period:", self))
            self._period_combo = QComboBox(self)
            period_bar.addWidget(self._period_combo, 1)
            self._post_selected_btn = QPushButton("Post Selected Line", self)
            self._post_selected_btn.setProperty("variant", "primary")
            self._post_selected_btn.clicked.connect(self._handle_post_selected)
            period_bar.addWidget(self._post_selected_btn)
            root.addLayout(period_bar)
            self._load_periods()
        else:
            self._period_combo = None  # type: ignore[assignment]
            self._post_selected_btn = None  # type: ignore[assignment]

        # Lines table
        self._table = QTableWidget(self)
        self._table.setColumnCount(len(self.COLUMNS))
        self._table.setHorizontalHeaderLabels(list(self.COLUMNS))
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self._table, 1)

        # Close button
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._refresh()

    # ── Private ───────────────────────────────────────────────────────

    def _refresh(self) -> None:
        # Reload from service
        try:
            dto = self._service_registry.deferral_service.get_schedule(
                self._schedule.company_id, self._schedule.id
            )
            self._schedule = dto
        except Exception:
            pass  # Use stale data on failure

        self._summary_label.setText(
            f"Total: {_money(self._schedule.total_amount)}  |  "
            f"Posted: {_money(self._schedule.posted_amount)}  |  "
            f"Remaining: {_money(self._schedule.remaining_amount)}  |  "
            f"Status: {self._schedule.status_code}"
        )

        self._table.setRowCount(len(self._schedule.lines))
        for row, line in enumerate(self._schedule.lines):
            self._table.setItem(row, 0, QTableWidgetItem(str(line.line_number)))
            self._table.setItem(row, 1, QTableWidgetItem(line.recognition_date.isoformat()))
            self._table.setItem(row, 2, _right(QTableWidgetItem(_money(line.amount))))
            status_item = QTableWidgetItem(line.status_code)
            if line.status_code == "POSTED":
                status_item.setForeground(Qt.GlobalColor.darkGreen)
            self._table.setItem(row, 3, status_item)
            je_text = str(line.journal_entry_id) if line.journal_entry_id else _DASH
            self._table.setItem(row, 4, QTableWidgetItem(je_text))

    def _load_periods(self) -> None:
        if self._period_combo is None:
            return
        try:
            periods = self._service_registry.fiscal_calendar_service.list_open_periods(
                self._schedule.company_id
            )
            self._period_combo.clear()
            for p in periods:
                self._period_combo.addItem(f"{p.period_code} — {p.period_name}", p.id)
        except Exception:
            pass

    def _current_period_id(self) -> int | None:
        if self._period_combo is None:
            return None
        idx = self._period_combo.currentIndex()
        if idx < 0:
            return None
        return self._period_combo.itemData(idx)

    def _selected_line(self) -> DeferralLineDTO | None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        row = rows[0].row()
        if row < 0 or row >= len(self._schedule.lines):
            return None
        return self._schedule.lines[row]

    def _handle_activate(self) -> None:
        from seeker_accounting.modules.accounting.deferrals.dto.deferral_dto import (
            ActivateDeferralScheduleCommand,
        )
        try:
            self._service_registry.deferral_service.activate_schedule(
                ActivateDeferralScheduleCommand(
                    company_id=self._schedule.company_id,
                    schedule_id=self._schedule.id,
                )
            )
            show_info(self, "Activated", "Schedule activated. Lines can now be posted.")
            self.accept()  # Close and let caller reload
        except (ValidationError, ConflictError) as exc:
            show_error(self, "Error", str(exc))
        except Exception as exc:
            show_error(self, "Error", f"Could not activate schedule: {exc}")

    def _handle_post_selected(self) -> None:
        line = self._selected_line()
        if line is None:
            show_error(self, "No selection", "Please select a PENDING line to post.")
            return
        if line.status_code != "PENDING":
            show_error(self, "Already posted", "The selected line is not in PENDING status.")
            return

        period_id = self._current_period_id()
        if period_id is None:
            show_error(self, "No period", "Please select a fiscal period to post to.")
            return

        cmd = PostRecognitionLineCommand(
            company_id=self._schedule.company_id,
            schedule_id=self._schedule.id,
            line_id=line.id,
            fiscal_period_id=period_id,
            posted_by_user_id=self._service_registry.app_context.current_user_id,
        )
        try:
            je_id = self._service_registry.deferral_service.post_recognition_line(cmd)
            show_info(self, "Posted", f"Recognition posted — Journal Entry #{je_id}.")
            self._refresh()
        except (ValidationError, ConflictError, NotFoundError) as exc:
            show_error(self, "Error", str(exc))
        except Exception as exc:
            show_error(self, "Error", f"Could not post recognition: {exc}")
