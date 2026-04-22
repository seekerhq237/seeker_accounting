from __future__ import annotations

import datetime
from decimal import Decimal

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.payroll.dto.payroll_payment_dto import (
    CreatePayrollPaymentRecordCommand,
)
from seeker_accounting.platform.exceptions import ValidationError
from seeker_accounting.shared.ui.message_boxes import show_error

_METHODS = [
    ("", "— Select method —"),
    ("manual_bank", "Manual Bank Transfer"),
    ("cash", "Cash"),
    ("cheque", "Cheque"),
    ("transfer_note", "Transfer Note"),
    ("other", "Other"),
]


class PayrollPaymentRecordDialog(QDialog):
    """Add a new payment record for one payroll run employee."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        run_employee_id: int,
        net_payable: Decimal,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._registry = service_registry
        self._company_id = company_id
        self._run_employee_id = run_employee_id
        self._net_payable = net_payable

        self.setWindowTitle("Record Payment")
        self.setMinimumWidth(400)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 12)
        layout.setSpacing(10)

        info = QLabel(f"Net Payable: {net_payable:,.2f}")
        info.setStyleSheet("font-weight: 600; font-size: 12px;")
        layout.addWidget(info)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)

        today = datetime.date.today()

        self._payment_date = QDateEdit()
        self._payment_date.setCalendarPopup(True)
        self._payment_date.setDisplayFormat("yyyy-MM-dd")
        self._payment_date.setDate(QDate(today.year, today.month, today.day))
        form.addRow("Payment Date:", self._payment_date)

        self._amount = QDoubleSpinBox()
        self._amount.setRange(0.01, 999_999_999.99)
        self._amount.setDecimals(2)
        self._amount.setValue(float(net_payable))
        form.addRow("Amount Paid:", self._amount)

        self._method = QComboBox()
        for code, label in _METHODS:
            self._method.addItem(label, code)
        form.addRow("Payment Method:", self._method)

        self._reference = QLineEdit()
        self._reference.setPlaceholderText("Bank ref, cheque no., etc.")
        form.addRow("Reference:", self._reference)

        self._notes = QTextEdit()
        self._notes.setMaximumHeight(54)
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
        install_help_button(self, "dialog.payroll_payment_record", dialog=True)

    def _on_accept(self) -> None:
        payment_date = self._payment_date.date().toPython()
        amount = Decimal(str(self._amount.value()))
        method_code = self._method.currentData() or None
        reference = self._reference.text().strip() or None
        notes = self._notes.toPlainText().strip() or None

        try:
            self._registry.payroll_payment_tracking_service.create_payment_record(
                self._company_id,
                CreatePayrollPaymentRecordCommand(
                    run_employee_id=self._run_employee_id,
                    payment_date=payment_date,
                    amount_paid=amount,
                    payment_method_code=method_code,
                    payment_reference=reference,
                    notes=notes,
                ),
            )
            self.accept()
        except Exception as exc:
            show_error(self, "Payment Record", str(exc))
