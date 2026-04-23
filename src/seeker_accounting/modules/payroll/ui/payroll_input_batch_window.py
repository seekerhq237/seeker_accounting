"""PayrollInputBatchWindow — child-window workbench for a payroll variable input batch.

Promoted from :class:`PayrollInputBatchDialog` in Slice P2. The window
reuses the existing ``_InputLineFormDialog`` for line create/edit and
calls the same ``payroll_input_service`` methods the dialog used.

Lifecycle is ribbon-driven:

* Add / Edit / Delete Line  (draft only)
* Approve Batch              (draft only)
* Void Batch                 (any non-voided status)
* Refresh / Close
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.shell.child_windows.child_window_base import ChildWindowBase
from seeker_accounting.app.shell.ribbon.ribbon_registry import RibbonRegistry
from seeker_accounting.modules.payroll.dto.payroll_calculation_dto import (
    PayrollInputBatchDetailDTO,
)
from seeker_accounting.modules.payroll.ui.dialogs.payroll_input_batch_dialog import (
    _InputLineFormDialog,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError
from seeker_accounting.shared.ui.icon_provider import IconProvider
from seeker_accounting.shared.ui.message_boxes import show_error
from seeker_accounting.shared.ui.table_helpers import configure_compact_table


_log = logging.getLogger(__name__)

_STATUS_LABELS = {
    "draft": "Draft",
    "approved": "Approved",
    "voided": "Voided",
}

_MONTHS = (
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


class PayrollInputBatchWindow(ChildWindowBase):
    """Child-window replacement for :class:`PayrollInputBatchDialog`."""

    DOC_TYPE = "payroll_input_batch"

    def __init__(
        self,
        service_registry: ServiceRegistry,
        *,
        company_id: int,
        batch_id: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            title="Variable Input Batch",
            surface_key=RibbonRegistry.child_window_key(self.DOC_TYPE),
            window_key=(self.DOC_TYPE, batch_id),
            registry=service_registry.ribbon_registry or RibbonRegistry(),
            icon_provider=IconProvider(service_registry.theme_manager),
            parent=parent,
        )
        self._registry = service_registry
        self._company_id = company_id
        self._batch_id = batch_id
        self._batch: PayrollInputBatchDetailDTO | None = None

        self.set_body(self._build_body())
        self._reload()

    # ── Body ──────────────────────────────────────────────────────────

    def _build_body(self) -> QWidget:
        body = QWidget(self)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        hero = QFrame(body)
        hero.setObjectName("DialogSectionCard")
        hero.setProperty("card", True)
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(18, 14, 18, 14)
        hero_layout.setSpacing(4)

        self._title_label = QLabel("Variable Input Batch", hero)
        self._title_label.setObjectName("DialogSectionTitle")
        hero_layout.addWidget(self._title_label)

        self._summary_label = QLabel(hero)
        self._summary_label.setObjectName("DialogSectionSummary")
        self._summary_label.setWordWrap(True)
        hero_layout.addWidget(self._summary_label)
        layout.addWidget(hero)

        self._table = QTableWidget(body)
        configure_compact_table(self._table)
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(
            ("Employee", "Component", "Type", "Amount", "Qty", "Notes")
        )
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.doubleClicked.connect(lambda *_: self._on_edit_line())
        self._table.selectionModel().selectionChanged.connect(
            lambda *_: self.refresh_ribbon_state()
        )
        layout.addWidget(self._table, 1)

        footer = QFrame(body)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        self._totals_label = QLabel("", footer)
        self._totals_label.setObjectName("DialogSectionSummary")
        footer_layout.addWidget(self._totals_label)
        footer_layout.addStretch(1)
        layout.addWidget(footer)

        return body

    # ── Data ──────────────────────────────────────────────────────────

    def _reload(self) -> None:
        try:
            batch = self._registry.payroll_input_service.get_batch(
                self._company_id, self._batch_id
            )
        except NotFoundError:
            show_error(self, "Variable Input Batch", "This batch no longer exists.")
            self.close()
            return
        except Exception as exc:  # noqa: BLE001 — surface any load failure
            show_error(self, "Variable Input Batch", str(exc))
            return

        self._batch = batch

        period_name = _MONTHS[batch.period_month] if 1 <= batch.period_month <= 12 else ""
        status_label = _STATUS_LABELS.get(batch.status_code, batch.status_code)
        self.setWindowTitle(f"Variable Input Batch — {batch.batch_reference}")
        self._title_label.setText(f"Batch {batch.batch_reference}")
        self._summary_label.setText(
            f"{period_name} {batch.period_year}  ·  Status: {status_label}"
            + (f"  ·  {batch.description}" if batch.description else "")
        )

        self._table.setRowCount(0)
        total_amount = 0
        for line in batch.lines:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(line.employee_display_name))
            self._table.setItem(row, 1, QTableWidgetItem(line.component_name))
            self._table.setItem(row, 2, QTableWidgetItem(line.component_type_code))
            amt = QTableWidgetItem(f"{line.input_amount:,.2f}")
            amt.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 3, amt)
            qty_text = str(line.input_quantity) if line.input_quantity is not None else ""
            self._table.setItem(row, 4, QTableWidgetItem(qty_text))
            self._table.setItem(row, 5, QTableWidgetItem(line.notes or ""))
            self._table.item(row, 0).setData(Qt.ItemDataRole.UserRole, line.id)
            total_amount += float(line.input_amount)

        self._table.resizeColumnsToContents()
        self._totals_label.setText(
            f"{len(batch.lines)} line(s)  ·  Total amount: {total_amount:,.2f}"
        )
        self.refresh_ribbon_state()

    def _selected_line_id(self) -> int | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    # ── Ribbon host implementation ────────────────────────────────────

    def handle_ribbon_command(self, command_id: str) -> None:  # type: ignore[override]
        dispatch = {
            "payroll_input_batch.add_line":    self._on_add_line,
            "payroll_input_batch.edit_line":   self._on_edit_line,
            "payroll_input_batch.delete_line": self._on_delete_line,
            "payroll_input_batch.approve":     self._on_approve,
            "payroll_input_batch.void":        self._on_void,
            "payroll_input_batch.refresh":     self._reload,
            "payroll_input_batch.close":       self.close,
        }
        handler = dispatch.get(command_id)
        if handler is not None:
            handler()

    def ribbon_state(self) -> dict[str, bool]:  # type: ignore[override]
        is_draft = self._batch is not None and self._batch.status_code == "draft"
        has_line = self._selected_line_id() is not None
        is_not_voided = self._batch is not None and self._batch.status_code != "voided"
        return {
            "payroll_input_batch.add_line":    is_draft,
            "payroll_input_batch.edit_line":   is_draft and has_line,
            "payroll_input_batch.delete_line": is_draft and has_line,
            "payroll_input_batch.approve":     is_draft and bool(self._batch and self._batch.lines),
            "payroll_input_batch.void":        is_not_voided,
            "payroll_input_batch.refresh":     True,
            "payroll_input_batch.close":       True,
        }

    # ── Command handlers ──────────────────────────────────────────────

    def _on_add_line(self) -> None:
        if self._batch is None or self._batch.status_code != "draft":
            return
        dlg = _InputLineFormDialog(
            self._registry, self._company_id, self._batch_id, None, self
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._reload()

    def _on_edit_line(self) -> None:
        if self._batch is None or self._batch.status_code != "draft":
            return
        line_id = self._selected_line_id()
        if line_id is None:
            return
        line = next((l for l in self._batch.lines if l.id == line_id), None)
        if line is None:
            return
        dlg = _InputLineFormDialog(
            self._registry, self._company_id, self._batch_id, line, self
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._reload()

    def _on_delete_line(self) -> None:
        line_id = self._selected_line_id()
        if line_id is None:
            return
        if QMessageBox.question(
            self, "Delete Line", "Delete this input line?"
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self._registry.payroll_input_service.delete_line(
                self._company_id, self._batch_id, line_id
            )
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "Variable Input Batch", str(exc))
            return
        self._reload()

    def _on_approve(self) -> None:
        if QMessageBox.question(
            self,
            "Approve Batch",
            "Approve this batch? It will be locked for editing.",
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self._registry.payroll_input_service.submit_batch(
                self._company_id, self._batch_id
            )
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "Variable Input Batch", str(exc))
            return
        self._reload()

    def _on_void(self) -> None:
        if QMessageBox.question(
            self, "Void Batch", "Void this batch?"
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self._registry.payroll_input_service.void_batch(
                self._company_id, self._batch_id
            )
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "Variable Input Batch", str(exc))
            return
        self._reload()
