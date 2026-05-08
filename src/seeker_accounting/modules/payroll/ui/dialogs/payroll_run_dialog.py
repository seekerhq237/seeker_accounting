from __future__ import annotations

import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.payroll.dto.payroll_calculation_dto import (
    CreateOffCyclePayrollRunCommand,
    CreatePayrollRunCommand,
)
from seeker_accounting.platform.exceptions import ConflictError, ValidationError
from seeker_accounting.shared.ui.message_boxes import show_configuration_error, show_error
from seeker_accounting.shared.ui.styles.inline_styles import text_style

_MONTHS = [
    (1, "January"), (2, "February"), (3, "March"), (4, "April"),
    (5, "May"), (6, "June"), (7, "July"), (8, "August"),
    (9, "September"), (10, "October"), (11, "November"), (12, "December"),
]


class PayrollRunDialog(QDialog):
    """Create a new payroll run header for a period."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._registry = service_registry
        self._company_id = company_id
        self._created_run_id: int | None = None

        self.setWindowTitle("Create payroll run")
        self.setMinimumWidth(420)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 12)
        layout.setSpacing(12)

        info_label = QLabel(
            "Creating a payroll run will reserve the period. "
            "Run 'Calculate' to process the selected scope."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet(text_style("secondary", font_size="11px"))
        layout.addWidget(info_label)

        form = QFormLayout()
        self._form = form
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)

        today = datetime.date.today()

        self._run_type = QComboBox()
        self._run_type.addItem("Regular payroll", "regular")
        self._run_type.addItem("Off-cycle payroll", "off_cycle")
        self._run_type.currentIndexChanged.connect(self._sync_run_type)
        form.addRow("Run Type:", self._run_type)

        self._year = QSpinBox()
        self._year.setRange(2000, 2100)
        self._year.setValue(today.year)
        form.addRow("Period Year:", self._year)

        self._month = QComboBox()
        for num, name in _MONTHS:
            self._month.addItem(name, num)
        self._month.setCurrentIndex(today.month - 1)
        form.addRow("Period Month:", self._month)

        self._run_label = QLineEdit()
        self._run_label.setPlaceholderText("Auto-generated if blank")
        form.addRow("Payroll run label:", self._run_label)

        self._currency = QLineEdit()
        self._currency.setText("XAF")
        self._currency.setMaxLength(3)
        self._currency.setFixedWidth(60)
        form.addRow("Currency:", self._currency)

        self._run_date = QDateEdit()
        self._run_date.setCalendarPopup(True)
        self._run_date.setDisplayFormat("yyyy-MM-dd")
        from PySide6.QtCore import QDate
        self._run_date.setDate(QDate(today.year, today.month, today.day))
        form.addRow("Payroll run date:", self._run_date)

        self._payment_date = QDateEdit()
        self._payment_date.setCalendarPopup(True)
        self._payment_date.setDisplayFormat("yyyy-MM-dd")
        self._payment_date.setSpecialValueText("Not set")
        self._payment_date.setDate(self._payment_date.minimumDate())
        form.addRow("Payment Date:", self._payment_date)

        self._notes = QTextEdit()
        self._notes.setMaximumHeight(60)
        self._notes.setPlaceholderText("Optional notes")
        form.addRow("Notes:", self._notes)

        self._offcycle_reason = QComboBox()
        for code, label in (
            ("missed_employee", "Missed employee"),
            ("bonus", "Bonus"),
            ("termination", "Termination"),
            ("retro_adjustment", "Retro adjustment"),
            ("manual_adjustment", "Manual adjustment"),
        ):
            self._offcycle_reason.addItem(label, code)
        form.addRow("Off-cycle reason:", self._offcycle_reason)

        self._employee_list = QListWidget()
        self._employee_list.setMinimumHeight(140)
        self._employee_list.setAlternatingRowColors(True)
        self._load_employees()
        form.addRow("Employees:", self._employee_list)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        from seeker_accounting.shared.ui.help_button import install_help_button
        install_help_button(self, "dialog.payroll_run", dialog=True)
        self._sync_run_type()

    @property
    def created_run_id(self) -> int | None:
        return self._created_run_id

    def _on_accept(self) -> None:
        currency = self._currency.text().strip().upper() or "XAF"
        run_date = self._run_date.date().toPython()
        pd = self._payment_date.date()
        payment_date = (
            pd.toPython()
            if pd != self._payment_date.minimumDate()
            else None
        )

        try:
            if self._run_type.currentData() == "off_cycle":
                result = self._registry.payroll_run_service.create_offcycle_run(
                    self._company_id,
                    CreateOffCyclePayrollRunCommand(
                        period_year=self._year.value(),
                        period_month=self._month.currentData(),
                        run_label=self._run_label.text().strip() or "",
                        currency_code=currency,
                        run_date=run_date,
                        payment_date=payment_date,
                        notes=self._notes.toPlainText().strip() or None,
                        employee_ids=self._selected_employee_ids(),
                        off_cycle_reason_code=str(self._offcycle_reason.currentData()),
                    ),
                )
            else:
                result = self._registry.payroll_run_service.create_run(
                    self._company_id,
                    CreatePayrollRunCommand(
                        period_year=self._year.value(),
                        period_month=self._month.currentData(),
                        run_label=self._run_label.text().strip() or "",
                        currency_code=currency,
                        run_date=run_date,
                        payment_date=payment_date,
                        notes=self._notes.toPlainText().strip() or None,
                    ),
                )
            self._created_run_id = result.id
            self.accept()
        except (ValidationError, ConflictError, Exception) as exc:
            error_msg = str(exc)
            if "document sequence" in error_msg.lower():
                from seeker_accounting.app.navigation import nav_ids
                if show_configuration_error(
                    self,
                    "Payroll run",
                    f"{error_msg}\n\nConfigure it in Accounting Setup \u2192 Document Sequences.",
                    "Open Document Sequences",
                ):
                    self._registry.navigation_service.navigate(nav_ids.DOCUMENT_SEQUENCES)
                    self.reject()
            else:
                show_error(self, "Payroll run", error_msg)

    def _sync_run_type(self) -> None:
        off_cycle = self._run_type.currentData() == "off_cycle"
        self._offcycle_reason.setVisible(off_cycle)
        self._employee_list.setVisible(off_cycle)
        for field in (self._offcycle_reason, self._employee_list):
            label = self._form.labelForField(field)
            if label is not None:
                label.setVisible(off_cycle)

    def _load_employees(self) -> None:
        self._employee_list.clear()
        try:
            employees = self._registry.employee_service.list_employees(
                self._company_id, active_only=True
            )
        except Exception:
            employees = []
        for employee in employees:
            item = QListWidgetItem(
                f"{employee.employee_number} - {employee.display_name}"
            )
            item.setData(Qt.ItemDataRole.UserRole, employee.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._employee_list.addItem(item)

    def _selected_employee_ids(self) -> tuple[int, ...]:
        ids: list[int] = []
        for index in range(self._employee_list.count()):
            item = self._employee_list.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                employee_id = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(employee_id, int):
                    ids.append(employee_id)
        return tuple(ids)
