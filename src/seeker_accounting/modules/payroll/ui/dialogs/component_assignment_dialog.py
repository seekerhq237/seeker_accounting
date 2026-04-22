from __future__ import annotations

import logging

from datetime import date
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.payroll.dto.payroll_calculation_dto import (
    ComponentAssignmentListItemDTO,
    CreateComponentAssignmentCommand,
    UpdateComponentAssignmentCommand,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError
from seeker_accounting.shared.ui.message_boxes import show_error

_log = logging.getLogger(__name__)


class ComponentAssignmentDialog(QDialog):
    """Assign a payroll component to an employee with optional overrides."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        employee_id: int,
        existing: ComponentAssignmentListItemDTO | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._registry = service_registry
        self._company_id = company_id
        self._employee_id = employee_id
        self._existing = existing

        self.setWindowTitle("Edit Component Assignment" if existing else "Assign Component")
        self.setMinimumWidth(400)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 12)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)

        self._component_combo = QComboBox()
        self._component_ids: list[int] = []
        self._load_components()
        form.addRow("Component:", self._component_combo)

        self._override_amount = QLineEdit()
        self._override_amount.setPlaceholderText("Leave blank to use component default")
        form.addRow("Override Amount:", self._override_amount)

        self._override_rate = QLineEdit()
        self._override_rate.setPlaceholderText("e.g. 0.042 for 4.2% — leave blank for default")
        form.addRow("Override Rate:", self._override_rate)

        self._effective_from = QDateEdit()
        self._effective_from.setCalendarPopup(True)
        self._effective_from.setDisplayFormat("yyyy-MM-dd")
        self._effective_from.setDate(_today())
        form.addRow("Effective From:", self._effective_from)

        self._effective_to = QDateEdit()
        self._effective_to.setCalendarPopup(True)
        self._effective_to.setDisplayFormat("yyyy-MM-dd")
        self._effective_to.setSpecialValueText("Open-ended")
        self._effective_to.setDate(self._effective_to.minimumDate())
        form.addRow("Effective To:", self._effective_to)

        self._is_active = QCheckBox("Active")
        self._is_active.setChecked(True)
        if existing is None:
            self._is_active.setVisible(False)
        form.addRow("", self._is_active)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        from seeker_accounting.shared.ui.help_button import install_help_button
        install_help_button(self, "dialog.component_assignment", dialog=True)

        if existing:
            self._populate(existing)

    def _load_components(self) -> None:
        try:
            company_id = self._company_id
            components = self._registry.payroll_component_service.list_components(
                company_id, active_only=True
            )
            self._component_ids = []
            for comp in components:
                self._component_combo.addItem(
                    f"{comp.component_code} — {comp.component_name}", comp.id
                )
                self._component_ids.append(comp.id)
        except Exception:
            _log.warning("Form data load error", exc_info=True)

    def _populate(self, dto: ComponentAssignmentListItemDTO) -> None:
        # Select the right component
        for i in range(self._component_combo.count()):
            if self._component_combo.itemData(i) == dto.component_id:
                self._component_combo.setCurrentIndex(i)
                break
        if dto.override_amount is not None:
            self._override_amount.setText(str(dto.override_amount))
        if dto.override_rate is not None:
            self._override_rate.setText(str(dto.override_rate))
        from PySide6.QtCore import QDate
        self._effective_from.setDate(QDate(dto.effective_from.year, dto.effective_from.month, dto.effective_from.day))
        if dto.effective_to:
            self._effective_to.setDate(QDate(dto.effective_to.year, dto.effective_to.month, dto.effective_to.day))
        self._is_active.setChecked(dto.is_active)

    def _on_accept(self) -> None:
        component_id = self._component_combo.currentData()
        if component_id is None:
            show_error(self, "Component Assignment", "Please select a payroll component.")
            return

        override_amount: Decimal | None = None
        raw_amt = self._override_amount.text().strip()
        if raw_amt:
            try:
                override_amount = Decimal(raw_amt)
            except InvalidOperation:
                show_error(self, "Component Assignment", "Override amount must be a valid number.")
                return

        override_rate: Decimal | None = None
        raw_rate = self._override_rate.text().strip()
        if raw_rate:
            try:
                override_rate = Decimal(raw_rate)
            except InvalidOperation:
                show_error(self, "Component Assignment", "Override rate must be a valid decimal (e.g. 0.042).")
                return

        effective_from = self._effective_from.date().toPython()
        to_date = self._effective_to.date()
        effective_to: date | None = (
            to_date.toPython()
            if to_date != self._effective_to.minimumDate()
            else None
        )

        try:
            svc = self._registry.component_assignment_service
            if self._existing is None:
                svc.create_assignment(
                    self._company_id,
                    CreateComponentAssignmentCommand(
                        employee_id=self._employee_id,
                        component_id=component_id,
                        effective_from=effective_from,
                        effective_to=effective_to,
                        override_amount=override_amount,
                        override_rate=override_rate,
                    ),
                )
            else:
                svc.update_assignment(
                    self._company_id,
                    self._existing.id,
                    UpdateComponentAssignmentCommand(
                        component_id=component_id,
                        effective_from=effective_from,
                        effective_to=effective_to,
                        is_active=self._is_active.isChecked(),
                        override_amount=override_amount,
                        override_rate=override_rate,
                    ),
                )
            self.accept()
        except (ValidationError, ConflictError, NotFoundError) as exc:
            show_error(self, "Component Assignment", str(exc))


def _today() -> "QDate":
    from PySide6.QtCore import QDate
    d = date.today()
    return QDate(d.year, d.month, d.day)
