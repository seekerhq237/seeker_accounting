from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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
from seeker_accounting.modules.accounting.reference_data.dto.tax_setup_dto import (
    CreateTaxCodeCommand,
    TaxCodeDTO,
    UpdateTaxCodeCommand,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.forms import create_field_block, create_label_value_row
from seeker_accounting.shared.ui.message_boxes import show_error

_TAX_TYPE_CODES: tuple[str, ...] = (
    "VAT",
    "WITHHOLDING",
    "SALES_TAX",
    "SERVICE_TAX",
)

_CALCULATION_METHOD_CODES: tuple[str, ...] = (
    "PERCENTAGE",
    "FIXED_AMOUNT",
    "EXEMPT",
)


class TaxCodeDialog(BaseDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        tax_code_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._tax_code_id = tax_code_id
        self._saved_tax_code: TaxCodeDTO | None = None

        title = "New Tax Code" if tax_code_id is None else "Edit Tax Code"
        super().__init__(title, parent, help_key="dialog.tax_code")
        self.setObjectName("TaxCodeDialog")
        self.resize(620, 520)

        intro_label = QLabel(
            "Define a company tax code with clear effective dates and a compact calculation setup suitable for first-pass accounting workflows.",
            self,
        )
        intro_label.setObjectName("PageSummary")
        intro_label.setWordWrap(True)
        self.body_layout.addWidget(intro_label)

        self.body_layout.addWidget(create_label_value_row("Company", company_name, self))

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        self.body_layout.addWidget(self._error_label)

        self.body_layout.addWidget(self._build_definition_section())
        self.body_layout.addWidget(self._build_effective_dates_section())
        self.body_layout.addStretch(1)

        self.button_box.setStandardButtons(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        self.button_box.accepted.connect(self._handle_submit)

        self._save_button = self.button_box.button(QDialogButtonBox.StandardButton.Save)
        if self._save_button is not None:
            self._save_button.setText("Create Tax Code" if tax_code_id is None else "Save Changes")
            self._save_button.setProperty("variant", "primary")

        cancel_button = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button is not None:
            cancel_button.setProperty("variant", "secondary")

        self._prepare_editable_combo(self._tax_type_combo, _TAX_TYPE_CODES, "Enter or select tax type")
        self._prepare_editable_combo(
            self._calculation_method_combo,
            _CALCULATION_METHOD_CODES,
            "Enter or select method",
        )
        self._populate_recoverable_combo()
        self._calculation_method_combo.currentTextChanged.connect(self._sync_rate_placeholder)
        self._has_effective_to_checkbox.toggled.connect(self._sync_effective_to_state)
        self._sync_rate_placeholder()
        self._sync_effective_to_state()

        if self._tax_code_id is not None:
            self._load_tax_code()
        else:
            self._suggest_code()

    @property
    def saved_tax_code(self) -> TaxCodeDTO | None:
        return self._saved_tax_code

    @classmethod
    def create_tax_code(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> TaxCodeDTO | None:
        dialog = cls(
            service_registry=service_registry,
            company_id=company_id,
            company_name=company_name,
            parent=parent,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_tax_code
        return None

    @classmethod
    def edit_tax_code(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        tax_code_id: int,
        parent: QWidget | None = None,
    ) -> TaxCodeDTO | None:
        dialog = cls(
            service_registry=service_registry,
            company_id=company_id,
            company_name=company_name,
            tax_code_id=tax_code_id,
            parent=parent,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_tax_code
        return None

    def _build_definition_section(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Definition", card)
        title.setObjectName("DialogSectionTitle")
        layout.addWidget(title)

        summary = QLabel(
            "Keep the tax definition code-driven and bounded. The dialog suggests common values but still leaves room for later approved vocabularies.",
            card,
        )
        summary.setObjectName("DialogSectionSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        self._code_edit = QLineEdit(card)
        self._code_edit.setPlaceholderText("VAT_STD")
        grid.addWidget(create_field_block("Code", self._code_edit), 0, 0)

        self._name_edit = QLineEdit(card)
        self._name_edit.setPlaceholderText("Standard VAT")
        grid.addWidget(create_field_block("Name", self._name_edit), 0, 1)

        self._tax_type_combo = QComboBox(card)
        self._tax_type_combo.setEditable(True)
        grid.addWidget(create_field_block("Tax Type", self._tax_type_combo), 1, 0)

        self._calculation_method_combo = QComboBox(card)
        self._calculation_method_combo.setEditable(True)
        grid.addWidget(create_field_block("Calculation Method", self._calculation_method_combo), 1, 1)

        self._rate_percent_edit = QLineEdit(card)
        self._rate_percent_edit.setPlaceholderText("19.25")
        grid.addWidget(create_field_block("Rate Percent", self._rate_percent_edit), 2, 0)

        self._recoverable_combo = QComboBox(card)
        grid.addWidget(create_field_block("Recoverable", self._recoverable_combo), 2, 1)

        layout.addLayout(grid)
        return card

    def _build_effective_dates_section(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Effective Dates", card)
        title.setObjectName("DialogSectionTitle")
        layout.addWidget(title)

        summary = QLabel(
            "Use an effective start date for each tax definition. Add an end date only when the code should stop being used.",
            card,
        )
        summary.setObjectName("DialogSectionSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        self._effective_from_edit = QDateEdit(card)
        self._effective_from_edit.setCalendarPopup(True)
        self._effective_from_edit.setDisplayFormat("yyyy-MM-dd")
        self._effective_from_edit.setDate(QDate.currentDate())
        grid.addWidget(create_field_block("Effective From", self._effective_from_edit), 0, 0)

        self._effective_to_edit = QDateEdit(card)
        self._effective_to_edit.setCalendarPopup(True)
        self._effective_to_edit.setDisplayFormat("yyyy-MM-dd")
        self._effective_to_edit.setDate(QDate.currentDate())
        grid.addWidget(create_field_block("Effective To", self._effective_to_edit), 0, 1)

        self._has_effective_to_checkbox = QCheckBox("Set an end date", card)
        grid.addWidget(self._has_effective_to_checkbox, 1, 0, 1, 2)

        layout.addLayout(grid)
        return card

    def _prepare_editable_combo(self, combo_box: QComboBox, codes: tuple[str, ...], placeholder: str) -> None:
        combo_box.clear()
        combo_box.addItem("")
        for code in codes:
            combo_box.addItem(code)
        combo_box.setCurrentIndex(0)
        line_edit = combo_box.lineEdit()
        if line_edit is not None:
            line_edit.setPlaceholderText(placeholder)

    def _populate_recoverable_combo(self) -> None:
        self._recoverable_combo.clear()
        self._recoverable_combo.addItem("Not specified", None)
        self._recoverable_combo.addItem("Yes", True)
        self._recoverable_combo.addItem("No", False)

    def _suggest_code(self) -> None:
        try:
            code = self._service_registry.code_suggestion_service.suggest("tax_code", self._company_id)
            self._code_edit.setText(code)
        except Exception:
            pass

    def _load_tax_code(self) -> None:
        try:
            tax_code = self._service_registry.tax_setup_service.get_tax_code(
                self._company_id,
                self._tax_code_id or 0,
            )
        except NotFoundError as exc:
            show_error(self, "Tax Code Not Found", str(exc))
            self.reject()
            return

        self._code_edit.setText(tax_code.code)
        self._name_edit.setText(tax_code.name)
        self._tax_type_combo.setEditText(tax_code.tax_type_code)
        self._calculation_method_combo.setEditText(tax_code.calculation_method_code)
        self._rate_percent_edit.setText("" if tax_code.rate_percent is None else str(tax_code.rate_percent))
        recoverable_index = self._recoverable_combo.findData(tax_code.is_recoverable)
        self._recoverable_combo.setCurrentIndex(recoverable_index if recoverable_index >= 0 else 0)
        self._effective_from_edit.setDate(self._to_qdate(tax_code.effective_from))
        if tax_code.effective_to is None:
            self._has_effective_to_checkbox.setChecked(False)
        else:
            self._has_effective_to_checkbox.setChecked(True)
            self._effective_to_edit.setDate(self._to_qdate(tax_code.effective_to))

    def _selected_code(self, combo_box: QComboBox) -> str:
        return combo_box.currentText().strip().upper()

    def _selected_recoverable(self) -> bool | None:
        value = self._recoverable_combo.currentData()
        if isinstance(value, bool):
            return value
        return None

    def _selected_effective_from(self) -> date:
        return self._effective_from_edit.date().toPython()

    def _selected_effective_to(self) -> date | None:
        if not self._has_effective_to_checkbox.isChecked():
            return None
        return self._effective_to_edit.date().toPython()

    def _parse_rate_percent(self) -> Decimal | None:
        raw_value = self._rate_percent_edit.text().strip()
        if not raw_value:
            return None
        try:
            return Decimal(raw_value)
        except InvalidOperation as exc:
            raise ValidationError("Rate percent must be a valid number.") from exc

    def _sync_rate_placeholder(self) -> None:
        calculation_method_code = self._selected_code(self._calculation_method_combo)
        if calculation_method_code == "PERCENTAGE":
            self._rate_percent_edit.setPlaceholderText("Required for percentage-based tax codes")
            return
        self._rate_percent_edit.setPlaceholderText("Optional")

    def _sync_effective_to_state(self) -> None:
        self._effective_to_edit.setEnabled(self._has_effective_to_checkbox.isChecked())

    def _set_error(self, message: str | None) -> None:
        if not message:
            self._error_label.clear()
            self._error_label.hide()
            return

        self._error_label.setText(message)
        self._error_label.show()

    def _to_qdate(self, value: date) -> QDate:
        return QDate(value.year, value.month, value.day)

    def _handle_submit(self) -> None:
        self._set_error(None)

        code = self._code_edit.text().strip()
        name = self._name_edit.text().strip()
        tax_type_code = self._selected_code(self._tax_type_combo)
        calculation_method_code = self._selected_code(self._calculation_method_combo)
        effective_from = self._selected_effective_from()
        effective_to = self._selected_effective_to()

        if not code:
            self._set_error("Code is required.")
            self._code_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        if not name:
            self._set_error("Name is required.")
            self._name_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        if not tax_type_code:
            self._set_error("Tax type is required.")
            self._tax_type_combo.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        if not calculation_method_code:
            self._set_error("Calculation method is required.")
            self._calculation_method_combo.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        if effective_to is not None and effective_to < effective_from:
            self._set_error("Effective to must be on or after effective from.")
            self._effective_to_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return

        try:
            rate_percent = self._parse_rate_percent()
        except ValidationError as exc:
            self._set_error(str(exc))
            self._rate_percent_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return

        if self._tax_code_id is None:
            command = CreateTaxCodeCommand(
                code=code,
                name=name,
                tax_type_code=tax_type_code,
                calculation_method_code=calculation_method_code,
                rate_percent=rate_percent,
                is_recoverable=self._selected_recoverable(),
                effective_from=effective_from,
                effective_to=effective_to,
            )
            save_operation = lambda: self._service_registry.tax_setup_service.create_tax_code(
                self._company_id,
                command,
            )
        else:
            command = UpdateTaxCodeCommand(
                code=code,
                name=name,
                tax_type_code=tax_type_code,
                calculation_method_code=calculation_method_code,
                rate_percent=rate_percent,
                is_recoverable=self._selected_recoverable(),
                effective_from=effective_from,
                effective_to=effective_to,
            )
            save_operation = lambda: self._service_registry.tax_setup_service.update_tax_code(
                self._company_id,
                self._tax_code_id,
                command,
            )

        try:
            self._saved_tax_code = save_operation()
        except (ValidationError, ConflictError) as exc:
            self._set_error(str(exc))
            return
        except NotFoundError as exc:
            show_error(self, "Tax Code Not Found", str(exc))
            return

        self.accept()

