from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.accounting.fiscal_periods.dto.fiscal_calendar_commands import (
    CreateFiscalYearCommand,
)
from seeker_accounting.modules.accounting.fiscal_periods.dto.fiscal_calendar_dto import FiscalYearDTO
from seeker_accounting.platform.exceptions import ConflictError, ValidationError
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.forms import create_field_block, create_label_value_row


class FiscalYearDialog(BaseDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._saved_fiscal_year: FiscalYearDTO | None = None

        super().__init__("New Fiscal Year", parent, help_key="dialog.fiscal_year")
        self.setObjectName("FiscalYearDialog")
        self.resize(540, 0)

        self.body_layout.addWidget(create_label_value_row("Company", company_name, self))

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        self.body_layout.addWidget(self._error_label)

        self.body_layout.addWidget(self._build_form_section())

        self.button_box.setStandardButtons(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        self.button_box.accepted.connect(self._handle_submit)

        save_button = self.button_box.button(QDialogButtonBox.StandardButton.Save)
        if save_button is not None:
            save_button.setText("Create Fiscal Year")
            save_button.setProperty("variant", "primary")

        cancel_button = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button is not None:
            cancel_button.setProperty("variant", "secondary")

        self._load_defaults()
        self.adjustSize()

    @property
    def saved_fiscal_year(self) -> FiscalYearDTO | None:
        return self._saved_fiscal_year

    @classmethod
    def create_fiscal_year(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> FiscalYearDTO | None:
        dialog = cls(service_registry, company_id, company_name, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_fiscal_year
        return None

    @classmethod
    def create_fiscal_year_for_date(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        target_date: date,
        parent: QWidget | None = None,
    ) -> FiscalYearDTO | None:
        """Open the fiscal year creation dialog with defaults pre-targeted to target_date's year."""
        dialog = cls(service_registry, company_id, company_name, parent=parent)
        dialog._apply_target_date(target_date)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_fiscal_year
        return None

    def _build_form_section(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(8)

        title = QLabel("Fiscal Year Definition", card)
        title.setObjectName("DialogSectionTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)

        self._year_code_edit = QLineEdit(card)
        self._year_code_edit.setPlaceholderText("FY2026")
        grid.addWidget(create_field_block("Year Code", self._year_code_edit), 0, 0)

        self._year_name_edit = QLineEdit(card)
        self._year_name_edit.setPlaceholderText("Fiscal Year 2026")
        grid.addWidget(create_field_block("Year Name", self._year_name_edit), 0, 1)

        self._start_date_edit = QDateEdit(card)
        self._start_date_edit.setCalendarPopup(True)
        self._start_date_edit.setDisplayFormat("yyyy-MM-dd")
        grid.addWidget(create_field_block("Start Date", self._start_date_edit), 1, 0)

        self._end_date_edit = QDateEdit(card)
        self._end_date_edit.setCalendarPopup(True)
        self._end_date_edit.setDisplayFormat("yyyy-MM-dd")
        grid.addWidget(create_field_block("End Date", self._end_date_edit), 1, 1)

        layout.addLayout(grid)
        return card

    def _load_defaults(self) -> None:
        today = date.today()
        start_date = date(today.year, 1, 1)
        end_date = date(today.year, 12, 31)
        self._year_code_edit.setText(f"FY{today.year}")
        self._year_name_edit.setText(f"Fiscal Year {today.year}")
        self._start_date_edit.setDate(QDate(start_date.year, start_date.month, start_date.day))
        self._end_date_edit.setDate(QDate(end_date.year, end_date.month, end_date.day))

    def _apply_target_date(self, target_date: date) -> None:
        """Override defaults to center the fiscal year on target_date's calendar year."""
        year = target_date.year
        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)
        self._year_code_edit.setText(f"FY{year}")
        self._year_name_edit.setText(f"Fiscal Year {year}")
        self._start_date_edit.setDate(QDate(start_date.year, start_date.month, start_date.day))
        self._end_date_edit.setDate(QDate(end_date.year, end_date.month, end_date.day))

    def _set_error(self, message: str | None) -> None:
        if not message:
            self._error_label.clear()
            self._error_label.hide()
            return
        self._error_label.setText(message)
        self._error_label.show()

    def _handle_submit(self) -> None:
        self._set_error(None)

        year_code = self._year_code_edit.text().strip()
        year_name = self._year_name_edit.text().strip()
        if not year_code:
            self._set_error("Fiscal year code is required.")
            self._year_code_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        if not year_name:
            self._set_error("Fiscal year name is required.")
            self._year_name_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return

        command = CreateFiscalYearCommand(
            year_code=year_code,
            year_name=year_name,
            start_date=self._start_date_edit.date().toPython(),
            end_date=self._end_date_edit.date().toPython(),
        )

        try:
            self._saved_fiscal_year = self._service_registry.fiscal_calendar_service.create_fiscal_year(
                self._company_id,
                command,
            )
        except (ValidationError, ConflictError) as exc:
            self._set_error(str(exc))
            return

        self.accept()
