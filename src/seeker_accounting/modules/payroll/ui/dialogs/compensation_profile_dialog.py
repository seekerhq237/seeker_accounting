from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.payroll.dto.payroll_calculation_dto import (
    CompensationProfileDetailDTO,
    CompensationProfileListItemDTO,
    CreateCompensationProfileCommand,
    UpdateCompensationProfileCommand,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError
from seeker_accounting.shared.ui.message_boxes import show_error


class CompensationProfileDialog(QDialog):
    """Create or edit an employee compensation profile."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        employee_id: int,
        employee_display_name: str,
        existing: CompensationProfileListItemDTO | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._registry = service_registry
        self._company_id = company_id
        self._employee_id = employee_id
        self._existing = existing

        self.setWindowTitle(
            "Edit Compensation Profile" if existing else "New Compensation Profile"
        )
        self.setMinimumWidth(420)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 12)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)

        self._profile_name = QLineEdit()
        self._profile_name.setPlaceholderText("e.g. Standard 2024")
        form.addRow("Profile Name:", self._profile_name)

        self._basic_salary = QLineEdit()
        self._basic_salary.setPlaceholderText("0.00")
        form.addRow(f"Basic Salary ({employee_display_name}):", self._basic_salary)

        self._currency = QLineEdit()
        self._currency.setMaxLength(3)
        self._currency.setFixedWidth(60)
        self._currency.setPlaceholderText("XAF")
        form.addRow("Currency:", self._currency)

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

        self._notes = QLineEdit()
        self._notes.setPlaceholderText("Optional notes")
        form.addRow("Notes:", self._notes)

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
        install_help_button(self, "dialog.compensation_profile", dialog=True)

        if existing:
            self._populate(existing)

    def _populate(self, dto: CompensationProfileListItemDTO) -> None:
        self._profile_name.setText(dto.profile_name)
        self._basic_salary.setText(str(dto.basic_salary))
        self._currency.setText(dto.currency_code)
        from PySide6.QtCore import QDate
        self._effective_from.setDate(QDate(dto.effective_from.year, dto.effective_from.month, dto.effective_from.day))
        if dto.effective_to:
            from PySide6.QtCore import QDate as QD
            self._effective_to.setDate(QD(dto.effective_to.year, dto.effective_to.month, dto.effective_to.day))
        self._is_active.setChecked(dto.is_active)

    def _on_accept(self) -> None:
        try:
            salary = Decimal(self._basic_salary.text().strip())
        except InvalidOperation:
            show_error(self, "Compensation Profile", "Basic salary must be a valid number.")
            return

        effective_from = self._effective_from.date().toPython()
        to_date = self._effective_to.date()
        effective_to: date | None = (
            to_date.toPython()
            if to_date != self._effective_to.minimumDate()
            else None
        )
        currency = self._currency.text().strip().upper() or "XAF"
        profile_name = self._profile_name.text().strip()
        if not profile_name:
            show_error(self, "Compensation Profile", "Profile name is required.")
            return

        try:
            svc = self._registry.compensation_profile_service
            if self._existing is None:
                svc.create_profile(
                    self._company_id,
                    CreateCompensationProfileCommand(
                        employee_id=self._employee_id,
                        profile_name=profile_name,
                        basic_salary=salary,
                        currency_code=currency,
                        effective_from=effective_from,
                        effective_to=effective_to,
                        notes=self._notes.text().strip() or None,
                    ),
                )
            else:
                svc.update_profile(
                    self._company_id,
                    self._existing.id,
                    UpdateCompensationProfileCommand(
                        profile_name=profile_name,
                        basic_salary=salary,
                        currency_code=currency,
                        effective_from=effective_from,
                        effective_to=effective_to,
                        is_active=self._is_active.isChecked(),
                        notes=self._notes.text().strip() or None,
                    ),
                )
            self.accept()
        except (ValidationError, ConflictError, NotFoundError) as exc:
            show_error(self, "Compensation Profile", str(exc))


def _today() -> "QDate":
    from PySide6.QtCore import QDate
    d = date.today()
    return QDate(d.year, d.month, d.day)
