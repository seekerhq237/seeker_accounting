from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.payroll.dto.payroll_correction_dto import (
    ApplyPayrollCorrectionCommand,
)
from seeker_accounting.platform.exceptions import AppError
from seeker_accounting.shared.ui.message_boxes import show_error

_REASONS: tuple[tuple[str, str], ...] = (
    ("missed_component", "Missed component"),
    ("retro_adjustment", "Retro adjustment"),
    ("tax_adjustment", "Tax adjustment"),
    ("benefit_adjustment", "Benefit adjustment"),
    ("manual_correction", "Manual correction"),
)


class PayrollCorrectionDialog(QDialog):
    """Queue an additive employee payroll correction."""

    def __init__(
        self,
        registry: ServiceRegistry,
        company_id: int,
        *,
        employee_id: int,
        employee_label: str,
        period_year: int,
        period_month: int,
        source_run_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._registry = registry
        self._company_id = company_id
        self._employee_id = employee_id
        self._period_year = period_year
        self._period_month = period_month
        self._source_run_id = source_run_id

        self.setWindowTitle("Queue Payroll Correction")
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 12)
        layout.setSpacing(10)

        intro = QLabel(
            f"Queue a correction for {employee_label}. It will be applied by the next eligible payroll calculation."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._component = QComboBox()
        try:
            components = registry.payroll_component_service.list_components(
                company_id, active_only=True
            )
        except Exception as exc:  # noqa: BLE001
            show_error(self, "Payroll correction", str(exc))
            components = []
        for component in components:
            if component.component_type_code == "informational":
                continue
            self._component.addItem(
                f"[{component.component_code}] {component.component_name}",
                component.id,
            )
        form.addRow("Payroll component:", self._component)

        self._amount = QDoubleSpinBox()
        self._amount.setRange(0.01, 999999999.99)
        self._amount.setDecimals(2)
        self._amount.setSingleStep(1000.00)
        self._amount.setAlignment(Qt.AlignmentFlag.AlignRight)
        form.addRow("Amount:", self._amount)

        self._reason = QComboBox()
        for code, label in _REASONS:
            self._reason.addItem(label, code)
        form.addRow("Reason:", self._reason)

        self._description = QPlainTextEdit()
        self._description.setMaximumHeight(80)
        self._description.setPlaceholderText("Optional explanation")
        form.addRow("Description:", self._description)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        component_id = self._component.currentData()
        if not isinstance(component_id, int):
            show_error(self, "Payroll Correction", "Select a payroll component.")
            return
        try:
            self._registry.payroll_correction_service.apply_correction(
                self._company_id,
                ApplyPayrollCorrectionCommand(
                    employee_id=self._employee_id,
                    component_id=component_id,
                    period_year=self._period_year,
                    period_month=self._period_month,
                    correction_amount=Decimal(str(self._amount.value())),
                    reason_code=str(self._reason.currentData()),
                    description=self._description.toPlainText().strip() or None,
                    source_run_id=self._source_run_id,
                ),
            )
        except AppError as exc:
            show_error(self, "Payroll Correction", str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            show_error(self, "Payroll Correction", str(exc))
            return
        self.accept()