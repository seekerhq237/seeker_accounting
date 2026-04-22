from __future__ import annotations

import logging

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.payroll.dto.payroll_calculation_dto import (
    CreatePayrollInputBatchCommand,
    CreatePayrollInputLineCommand,
    PayrollInputBatchDetailDTO,
    PayrollInputLineDTO,
    UpdatePayrollInputLineCommand,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError
from seeker_accounting.shared.ui.message_boxes import show_configuration_error, show_error
from seeker_accounting.shared.ui.table_helpers import configure_compact_table

_log = logging.getLogger(__name__)

_STATUS_LABELS = {
    "draft": "Draft",
    "approved": "Approved",
    "voided": "Voided",
}

_MONTHS = [
    (1, "January"), (2, "February"), (3, "March"), (4, "April"),
    (5, "May"), (6, "June"), (7, "July"), (8, "August"),
    (9, "September"), (10, "October"), (11, "November"), (12, "December"),
]


class NewPayrollInputBatchDialog(QDialog):
    """Create a new payroll variable input batch."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._registry = service_registry
        self._company_id = company_id
        self._created_id: int | None = None

        self.setWindowTitle("New Variable Input Batch")
        self.setMinimumWidth(360)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 12)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)

        import datetime
        today = datetime.date.today()

        self._year = QSpinBox()
        self._year.setRange(2000, 2100)
        self._year.setValue(today.year)
        form.addRow("Period Year:", self._year)

        self._month = QComboBox()
        for num, name in _MONTHS:
            self._month.addItem(name, num)
        self._month.setCurrentIndex(today.month - 1)
        form.addRow("Period Month:", self._month)

        self._description = QLineEdit()
        self._description.setPlaceholderText("Optional description")
        form.addRow("Description:", self._description)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def created_batch_id(self) -> int | None:
        return self._created_id

    def _on_accept(self) -> None:
        try:
            result = self._registry.payroll_input_service.create_batch(
                self._company_id,
                CreatePayrollInputBatchCommand(
                    period_year=self._year.value(),
                    period_month=self._month.currentData(),
                    description=self._description.text().strip() or None,
                ),
            )
            self._created_id = result.id
            self.accept()
        except (ValidationError, Exception) as exc:
            error_msg = str(exc)
            if "document sequence" in error_msg.lower():
                from seeker_accounting.app.navigation import nav_ids
                if show_configuration_error(
                    self,
                    "Payroll Input Batch",
                    f"{error_msg}\n\nConfigure it in Accounting Setup \u2192 Document Sequences.",
                    "Open Document Sequences",
                ):
                    self._registry.navigation_service.navigate(nav_ids.DOCUMENT_SEQUENCES)
                    self.reject()
            else:
                show_error(self, "Payroll Input Batch", error_msg)


class PayrollInputBatchDialog(QDialog):
    """View and manage lines within a payroll input batch."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        batch_id: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._registry = service_registry
        self._company_id = company_id
        self._batch_id = batch_id

        self.setWindowTitle("Variable Input Batch")
        self.setMinimumSize(720, 500)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 12)
        layout.setSpacing(10)

        self._header_label = QLabel()
        self._header_label.setStyleSheet("font-weight: 600; font-size: 13px;")
        layout.addWidget(self._header_label)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        self._btn_add = QPushButton("Add Line")
        self._btn_edit = QPushButton("Edit")
        self._btn_delete = QPushButton("Delete")
        self._btn_approve = QPushButton("Approve Batch")
        self._btn_void = QPushButton("Void Batch")
        for btn in (self._btn_add, self._btn_edit, self._btn_delete, self._btn_approve, self._btn_void):
            btn.setFixedHeight(26)
            toolbar.addWidget(btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # Table
        self._table = QTableWidget()
        configure_compact_table(self._table)
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels([
            "Employee", "Component", "Type", "Amount", "Qty", "Notes"
        ])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        layout.addWidget(self._table)

        close_btn = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_btn.rejected.connect(self.reject)
        layout.addWidget(close_btn)

        self._btn_add.clicked.connect(self._on_add)
        self._btn_edit.clicked.connect(self._on_edit)
        self._btn_delete.clicked.connect(self._on_delete)
        self._btn_approve.clicked.connect(self._on_approve)
        self._btn_void.clicked.connect(self._on_void)

        from seeker_accounting.shared.ui.help_button import install_help_button
        install_help_button(self, "dialog.payroll_input_batch", dialog=True)

        self._refresh()

    def _refresh(self) -> None:
        try:
            batch = self._registry.payroll_input_service.get_batch(
                self._company_id, self._batch_id
            )
        except NotFoundError:
            self.reject()
            return

        month_name = _MONTHS[batch.period_month - 1][1]
        self._header_label.setText(
            f"{batch.batch_reference}  ·  {month_name} {batch.period_year}  ·  "
            f"Status: {_STATUS_LABELS.get(batch.status_code, batch.status_code)}"
        )

        is_draft = batch.status_code == "draft"
        self._btn_add.setEnabled(is_draft)
        self._btn_edit.setEnabled(is_draft)
        self._btn_delete.setEnabled(is_draft)
        self._btn_approve.setEnabled(is_draft)
        self._btn_void.setEnabled(batch.status_code not in ("voided",))

        self._table.setRowCount(0)
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

        self._table.resizeColumnsToContents()
        self._batch = batch

    def _selected_line_id(self) -> int | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_add(self) -> None:
        dlg = _InputLineFormDialog(
            self._registry, self._company_id, self._batch_id, None, self
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._refresh()

    def _on_edit(self) -> None:
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
            self._refresh()

    def _on_delete(self) -> None:
        line_id = self._selected_line_id()
        if line_id is None:
            return
        if QMessageBox.question(self, "Delete Line", "Delete this input line?") != QMessageBox.StandardButton.Yes:
            return
        try:
            self._registry.payroll_input_service.delete_line(
                self._company_id, self._batch_id, line_id
            )
            self._refresh()
        except Exception as exc:
            show_error(self, "Payroll Input Batch", str(exc))

    def _on_approve(self) -> None:
        if QMessageBox.question(
            self, "Approve Batch", "Approve this batch? It will be locked for editing."
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self._registry.payroll_input_service.submit_batch(
                self._company_id, self._batch_id
            )
            self._refresh()
        except Exception as exc:
            show_error(self, "Payroll Input Batch", str(exc))

    def _on_void(self) -> None:
        if QMessageBox.question(self, "Void Batch", "Void this batch?") != QMessageBox.StandardButton.Yes:
            return
        try:
            self._registry.payroll_input_service.void_batch(
                self._company_id, self._batch_id
            )
            self._refresh()
        except Exception as exc:
            show_error(self, "Payroll Input Batch", str(exc))


class _InputLineFormDialog(QDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        batch_id: int,
        existing: PayrollInputLineDTO | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._registry = service_registry
        self._company_id = company_id
        self._batch_id = batch_id
        self._existing = existing

        self.setWindowTitle("Edit Line" if existing else "Add Input Line")
        self.setMinimumWidth(380)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 10)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)

        self._employee_combo = QComboBox()
        self._employee_ids: list[int] = []
        self._component_combo = QComboBox()
        self._component_ids: list[int] = []

        self._load_employees()
        self._load_components()

        form.addRow("Employee:", self._employee_combo)
        form.addRow("Component:", self._component_combo)

        self._amount = QLineEdit()
        self._amount.setPlaceholderText("0.00")
        form.addRow("Amount:", self._amount)

        self._quantity = QLineEdit()
        self._quantity.setPlaceholderText("Optional (e.g. hours for overtime)")
        form.addRow("Quantity:", self._quantity)

        self._notes = QLineEdit()
        self._notes.setPlaceholderText("Optional")
        form.addRow("Notes:", self._notes)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if existing:
            self._populate(existing)

    def _load_employees(self) -> None:
        try:
            employees = self._registry.employee_service.list_employees(
                self._company_id, active_only=True
            )
            for emp in employees:
                self._employee_combo.addItem(
                    f"{emp.employee_number} — {emp.display_name}", emp.id
                )
                self._employee_ids.append(emp.id)
        except Exception:
            _log.warning("Form data load error", exc_info=True)

    def _load_components(self) -> None:
        try:
            components = self._registry.payroll_component_service.list_components(
                self._company_id, active_only=True
            )
            for comp in components:
                self._component_combo.addItem(
                    f"{comp.component_code} — {comp.component_name}", comp.id
                )
                self._component_ids.append(comp.id)
        except Exception:
            _log.warning("Form data load error", exc_info=True)

    def _populate(self, dto: PayrollInputLineDTO) -> None:
        for i in range(self._employee_combo.count()):
            if self._employee_combo.itemData(i) == dto.employee_id:
                self._employee_combo.setCurrentIndex(i)
                break
        for i in range(self._component_combo.count()):
            if self._component_combo.itemData(i) == dto.component_id:
                self._component_combo.setCurrentIndex(i)
                break
        self._amount.setText(str(dto.input_amount))
        if dto.input_quantity is not None:
            self._quantity.setText(str(dto.input_quantity))
        self._notes.setText(dto.notes or "")

    def _on_accept(self) -> None:
        employee_id = self._employee_combo.currentData()
        component_id = self._component_combo.currentData()
        if not employee_id or not component_id:
            show_error(self, "Payroll Input Batch", "Select employee and component.")
            return
        try:
            amount = Decimal(self._amount.text().strip())
        except InvalidOperation:
            show_error(self, "Payroll Input Batch", "Amount must be a valid number.")
            return
        qty_text = self._quantity.text().strip()
        try:
            quantity = Decimal(qty_text) if qty_text else None
        except InvalidOperation:
            show_error(self, "Payroll Input Batch", "Quantity must be a valid number.")
            return

        try:
            svc = self._registry.payroll_input_service
            if self._existing is None:
                svc.add_line(
                    self._company_id,
                    self._batch_id,
                    CreatePayrollInputLineCommand(
                        employee_id=employee_id,
                        component_id=component_id,
                        input_amount=amount,
                        input_quantity=quantity,
                        notes=self._notes.text().strip() or None,
                    ),
                )
            else:
                svc.update_line(
                    self._company_id,
                    self._batch_id,
                    self._existing.id,
                    UpdatePayrollInputLineCommand(
                        input_amount=amount,
                        input_quantity=quantity,
                        notes=self._notes.text().strip() or None,
                    ),
                )
            self.accept()
        except (ValidationError, NotFoundError, Exception) as exc:
            show_error(self, "Payroll Input Batch", str(exc))
