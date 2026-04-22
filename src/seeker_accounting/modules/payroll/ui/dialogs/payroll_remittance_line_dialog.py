from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.payroll.dto.payroll_remittance_dto import (
    CreatePayrollRemittanceLineCommand,
)
from seeker_accounting.shared.ui.message_boxes import show_error


class PayrollRemittanceLineDialog(QDialog):
    """Add a detail line to a remittance batch."""

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

        self.setWindowTitle("Add Remittance Line")
        self.setMinimumWidth(380)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 12)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)

        self._description = QLineEdit()
        self._description.setPlaceholderText("e.g. IRPP for January 2025")
        form.addRow("Description:", self._description)

        self._amount_due = QDoubleSpinBox()
        self._amount_due.setRange(0, 999_999_999.99)
        self._amount_due.setDecimals(2)
        form.addRow("Amount Due:", self._amount_due)

        self._notes = QTextEdit()
        self._notes.setMaximumHeight(48)
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
        install_help_button(self, "dialog.payroll_remittance_line", dialog=True)

    def _on_accept(self) -> None:
        description = self._description.text().strip()
        if not description:
            show_error(self, "Remittance Line", "Description is required.")
            return
        try:
            self._registry.payroll_remittance_service.add_line(
                self._company_id,
                self._batch_id,
                CreatePayrollRemittanceLineCommand(
                    description=description,
                    amount_due=Decimal(str(self._amount_due.value())),
                    notes=self._notes.toPlainText().strip() or None,
                ),
            )
            self.accept()
        except Exception as exc:
            show_error(self, "Remittance Line", str(exc))
