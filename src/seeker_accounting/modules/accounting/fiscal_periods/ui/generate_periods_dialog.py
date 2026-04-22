from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFrame, QLabel, QVBoxLayout, QWidget

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.accounting.fiscal_periods.dto.fiscal_calendar_commands import (
    GenerateFiscalPeriodsCommand,
)
from seeker_accounting.modules.accounting.fiscal_periods.dto.fiscal_calendar_dto import FiscalCalendarDTO
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.forms import create_label_value_row


class GeneratePeriodsDialog(BaseDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        fiscal_year_id: int,
        fiscal_year_code: str,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._fiscal_year_id = fiscal_year_id
        self._generated_calendar: FiscalCalendarDTO | None = None

        super().__init__("Generate Fiscal Periods", parent, help_key="dialog.generate_periods")
        self.setObjectName("GeneratePeriodsDialog")
        self.resize(560, 320)

        intro_label = QLabel(
            "Generate the company calendar from the fiscal year boundary using the locked first-pass monthly pattern.",
            self,
        )
        intro_label.setObjectName("PageSummary")
        intro_label.setWordWrap(True)
        self.body_layout.addWidget(intro_label)
        self.body_layout.addWidget(create_label_value_row("Company", company_name, self))
        self.body_layout.addWidget(create_label_value_row("Fiscal Year", fiscal_year_code, self))

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        self.body_layout.addWidget(self._error_label)

        self.body_layout.addWidget(self._build_summary_card())
        self.body_layout.addStretch(1)

        self.button_box.setStandardButtons(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        self.button_box.accepted.connect(self._handle_submit)

        save_button = self.button_box.button(QDialogButtonBox.StandardButton.Save)
        if save_button is not None:
            save_button.setText("Generate Periods")
            save_button.setProperty("variant", "primary")

        cancel_button = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button is not None:
            cancel_button.setProperty("variant", "secondary")

    @property
    def generated_calendar(self) -> FiscalCalendarDTO | None:
        return self._generated_calendar

    @classmethod
    def generate_periods(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        fiscal_year_id: int,
        fiscal_year_code: str,
        parent: QWidget | None = None,
    ) -> FiscalCalendarDTO | None:
        dialog = cls(
            service_registry=service_registry,
            company_id=company_id,
            company_name=company_name,
            fiscal_year_id=fiscal_year_id,
            fiscal_year_code=fiscal_year_code,
            parent=parent,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.generated_calendar
        return None

    def _build_summary_card(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(10)

        title = QLabel("Generation Pattern", card)
        title.setObjectName("DialogSectionTitle")
        layout.addWidget(title)

        summary = QLabel(
            "This first pass creates 12 monthly periods and leaves adjustment-period generation for a later controlled extension.",
            card,
        )
        summary.setObjectName("DialogSectionSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)
        return card

    def _set_error(self, message: str | None) -> None:
        if not message:
            self._error_label.clear()
            self._error_label.hide()
            return
        self._error_label.setText(message)
        self._error_label.show()

    def _handle_submit(self) -> None:
        self._set_error(None)
        try:
            self._generated_calendar = self._service_registry.fiscal_calendar_service.generate_periods(
                self._company_id,
                self._fiscal_year_id,
                GenerateFiscalPeriodsCommand(),
            )
        except (ValidationError, ConflictError, NotFoundError) as exc:
            self._set_error(str(exc))
            return
        self.accept()
