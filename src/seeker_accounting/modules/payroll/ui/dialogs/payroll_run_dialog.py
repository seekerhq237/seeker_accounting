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
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.payroll.dto.payroll_calculation_dto import (
    CreatePayrollRunCommand,
)
from seeker_accounting.platform.exceptions import ConflictError, ValidationError
from seeker_accounting.shared.ui.message_boxes import show_configuration_error, show_error

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

        self.setWindowTitle("Create Payroll Run")
        self.setMinimumWidth(420)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 12)
        layout.setSpacing(12)

        info_label = QLabel(
            "Creating a payroll run will reserve the period. "
            "Run 'Calculate' to process all active employees."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(info_label)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)

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

        self._run_label = QLineEdit()
        self._run_label.setPlaceholderText("Auto-generated if blank")
        form.addRow("Run Label:", self._run_label)

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
        form.addRow("Run Date:", self._run_date)

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

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        from seeker_accounting.shared.ui.help_button import install_help_button
        install_help_button(self, "dialog.payroll_run", dialog=True)

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
                    "Payroll Run",
                    f"{error_msg}\n\nConfigure it in Accounting Setup \u2192 Document Sequences.",
                    "Open Document Sequences",
                ):
                    self._registry.navigation_service.navigate(nav_ids.DOCUMENT_SEQUENCES)
                    self.reject()
            else:
                show_error(self, "Payroll Run", error_msg)
