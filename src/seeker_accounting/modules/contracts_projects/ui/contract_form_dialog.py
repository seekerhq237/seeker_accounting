from __future__ import annotations

import logging

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.contracts_projects.dto.contract_dto import (
    ContractDetailDTO,
    CreateContractCommand,
    UpdateContractCommand,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.forms import create_field_block, create_label_value_row
from seeker_accounting.shared.ui.message_boxes import show_error
from seeker_accounting.shared.ui.searchable_combo_box import SearchableComboBox

_log = logging.getLogger(__name__)


class ContractFormDialog(BaseDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        contract_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._contract_id = contract_id
        self._saved_contract: ContractDetailDTO | None = None

        title = "New Contract" if contract_id is None else "Edit Contract"
        super().__init__(title, parent, help_key="dialog.contract_form")
        self.setObjectName("ContractFormDialog")
        self.resize(780, 640)

        intro_label = QLabel(
            "Define contract master data scoped to the active company. "
            "Status transitions are controlled by service rules.",
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

        self.body_layout.addWidget(self._build_identity_section())
        self.body_layout.addWidget(self._build_terms_section())
        self.body_layout.addWidget(self._build_notes_section())
        self.body_layout.addStretch(1)

        self.button_box.setStandardButtons(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        self.button_box.accepted.connect(self._handle_submit)

        save_button = self.button_box.button(QDialogButtonBox.StandardButton.Save)
        if save_button is not None:
            save_button.setText("Create Contract" if contract_id is None else "Save Changes")
            save_button.setProperty("variant", "primary")

        cancel_button = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button is not None:
            cancel_button.setProperty("variant", "secondary")

        self._load_reference_data()
        if self._contract_id is not None:
            self._load_contract()
        else:
            self._suggest_code()

    @property
    def saved_contract(self) -> ContractDetailDTO | None:
        return self._saved_contract

    @classmethod
    def create_contract(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> ContractDetailDTO | None:
        dialog = cls(service_registry, company_id, company_name, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_contract
        return None

    @classmethod
    def edit_contract(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        contract_id: int,
        parent: QWidget | None = None,
    ) -> ContractDetailDTO | None:
        dialog = cls(
            service_registry=service_registry,
            company_id=company_id,
            company_name=company_name,
            contract_id=contract_id,
            parent=parent,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_contract
        return None

    # ------------------------------------------------------------------
    # Form sections
    # ------------------------------------------------------------------

    def _build_identity_section(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Identity", card)
        title.setObjectName("DialogSectionTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        self._contract_number_edit = QLineEdit(card)
        self._contract_number_edit.setPlaceholderText("CTR-001")
        grid.addWidget(create_field_block("Contract Number", self._contract_number_edit), 0, 0)

        self._contract_title_edit = QLineEdit(card)
        self._contract_title_edit.setPlaceholderText("Service agreement title")
        grid.addWidget(create_field_block("Contract Title", self._contract_title_edit), 0, 1)

        self._customer_combo = SearchableComboBox(card)
        self._customer_combo.setMaxVisibleItems(18)
        grid.addWidget(create_field_block("Customer", self._customer_combo), 1, 0)

        self._contract_type_combo = QComboBox(card)
        self._contract_type_combo.addItem("Fixed Price", "fixed_price")
        self._contract_type_combo.addItem("Time and Material", "time_and_material")
        self._contract_type_combo.addItem("Cost Plus", "cost_plus")
        self._contract_type_combo.addItem("Framework", "framework")
        self._contract_type_combo.addItem("Other", "other")
        grid.addWidget(create_field_block("Contract Type", self._contract_type_combo), 1, 1)

        layout.addLayout(grid)
        return card

    def _build_terms_section(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Terms and Dates", card)
        title.setObjectName("DialogSectionTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        self._currency_combo = SearchableComboBox(card)
        self._currency_combo.setMaxVisibleItems(18)
        grid.addWidget(create_field_block("Currency", self._currency_combo), 0, 0)

        self._base_amount_edit = QLineEdit(card)
        self._base_amount_edit.setPlaceholderText("0.00")
        grid.addWidget(
            create_field_block("Base Contract Amount", self._base_amount_edit, "Leave blank if not yet defined."),
            0, 1,
        )

        self._start_date_edit = QDateEdit(card)
        self._start_date_edit.setCalendarPopup(True)
        self._start_date_edit.setDisplayFormat("yyyy-MM-dd")
        grid.addWidget(create_field_block("Start Date", self._start_date_edit), 1, 0)

        self._planned_end_date_edit = QDateEdit(card)
        self._planned_end_date_edit.setCalendarPopup(True)
        self._planned_end_date_edit.setDisplayFormat("yyyy-MM-dd")
        grid.addWidget(create_field_block("Planned End Date", self._planned_end_date_edit), 1, 1)

        self._billing_basis_combo = QComboBox(card)
        self._billing_basis_combo.addItem("No billing basis", "")
        self._billing_basis_combo.addItem("Milestone", "milestone")
        self._billing_basis_combo.addItem("Progress", "progress")
        self._billing_basis_combo.addItem("Time and Material", "time_and_material")
        self._billing_basis_combo.addItem("Fixed Schedule", "fixed_schedule")
        self._billing_basis_combo.addItem("Manual", "manual")
        grid.addWidget(create_field_block("Billing Basis", self._billing_basis_combo), 2, 0)

        self._retention_edit = QLineEdit(card)
        self._retention_edit.setPlaceholderText("e.g. 5.00")
        grid.addWidget(
            create_field_block("Retention %", self._retention_edit, "Leave blank for no retention."),
            2, 1,
        )

        self._reference_number_edit = QLineEdit(card)
        grid.addWidget(create_field_block("Reference Number", self._reference_number_edit), 3, 0)

        layout.addLayout(grid)
        return card

    def _build_notes_section(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Description", card)
        title.setObjectName("DialogSectionTitle")
        layout.addWidget(title)

        self._description_edit = QPlainTextEdit(card)
        self._description_edit.setPlaceholderText("Optional contract description")
        self._description_edit.setFixedHeight(92)
        layout.addWidget(self._description_edit)

        return card

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _suggest_code(self) -> None:
        try:
            code = self._service_registry.code_suggestion_service.suggest("contract", self._company_id)
            self._contract_number_edit.setText(code)
        except Exception:
            pass

    def _load_reference_data(self) -> None:
        try:
            customers = self._service_registry.customer_service.list_customers(
                self._company_id, active_only=True
            )
            self._customer_combo.set_items(
                [(f"{c.customer_code} — {c.display_name}", c.id) for c in customers],
                placeholder="-- Select customer --",
                placeholder_value=0,
            )
        except Exception:
            _log.warning("Form data load error", exc_info=True)

        try:
            currencies = self._service_registry.reference_data_service.list_active_currencies()
            self._currency_combo.set_items(
                [(cur.code, cur.code) for cur in currencies],
                placeholder="-- Select currency --",
            )
            ctx = self._service_registry.active_company_context
            if ctx.base_currency_code:
                self._currency_combo.set_current_value(ctx.base_currency_code)
        except Exception:
            _log.warning("Form data load error", exc_info=True)

    def _load_contract(self) -> None:
        try:
            contract = self._service_registry.contract_service.get_contract_detail(
                self._contract_id or 0
            )
        except NotFoundError as exc:
            show_error(self, "Contract Not Found", str(exc))
            self.reject()
            return

        self._contract_number_edit.setText(contract.contract_number)
        self._contract_title_edit.setText(contract.contract_title)
        self._customer_combo.set_current_value(contract.customer_id)
        self._select_combo_data(self._contract_type_combo, contract.contract_type_code)
        self._currency_combo.set_current_value(contract.currency_code)
        self._base_amount_edit.setText(
            "" if contract.base_contract_amount is None else str(contract.base_contract_amount)
        )
        if contract.start_date:
            self._start_date_edit.setDate(contract.start_date)
        if contract.planned_end_date:
            self._planned_end_date_edit.setDate(contract.planned_end_date)
        self._select_combo_data(self._billing_basis_combo, contract.billing_basis_code or "")
        self._retention_edit.setText(
            "" if contract.retention_percent is None else str(contract.retention_percent)
        )
        self._reference_number_edit.setText(contract.reference_number or "")
        self._description_edit.setPlainText(contract.description or "")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _select_combo_data(self, combo: QComboBox, value: object) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)

    def _selected_customer_id(self) -> int:
        value = self._customer_combo.current_value()
        return value if isinstance(value, int) and value > 0 else 0

    def _parse_decimal(self, text: str, field_name: str) -> Decimal | None:
        text = text.strip()
        if not text:
            return None
        try:
            return Decimal(text)
        except InvalidOperation as exc:
            raise ValidationError(f"{field_name} must be a valid number.") from exc

    def _set_error(self, message: str | None) -> None:
        if not message:
            self._error_label.clear()
            self._error_label.hide()
            return
        self._error_label.setText(message)
        self._error_label.show()

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------

    def _handle_submit(self) -> None:
        self._set_error(None)

        contract_number = self._contract_number_edit.text().strip()
        contract_title = self._contract_title_edit.text().strip()
        if not contract_number:
            self._set_error("Contract number is required.")
            self._contract_number_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        if not contract_title:
            self._set_error("Contract title is required.")
            self._contract_title_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return

        customer_id = self._selected_customer_id()
        if customer_id == 0:
            self._set_error("Select a customer.")
            return

        currency_code = self._currency_combo.current_value()
        if not currency_code:
            self._set_error("Select a currency.")
            return

        try:
            base_amount = self._parse_decimal(self._base_amount_edit.text(), "Base contract amount")
            retention = self._parse_decimal(self._retention_edit.text(), "Retention percent")
        except ValidationError as exc:
            self._set_error(str(exc))
            return

        billing_basis = self._billing_basis_combo.currentData()
        start_date = self._start_date_edit.date().toPython()
        planned_end_date = self._planned_end_date_edit.date().toPython()

        try:
            if self._contract_id is None:
                self._saved_contract = self._service_registry.contract_service.create_contract(
                    CreateContractCommand(
                        company_id=self._company_id,
                        contract_number=contract_number,
                        contract_title=contract_title,
                        customer_id=customer_id,
                        contract_type_code=self._contract_type_combo.currentData() or "other",
                        currency_code=currency_code,
                        base_contract_amount=base_amount,
                        start_date=start_date,
                        planned_end_date=planned_end_date,
                        billing_basis_code=billing_basis or None,
                        retention_percent=retention,
                        reference_number=self._reference_number_edit.text().strip() or None,
                        description=self._description_edit.toPlainText().strip() or None,
                    )
                )
            else:
                self._saved_contract = self._service_registry.contract_service.update_contract(
                    self._contract_id,
                    UpdateContractCommand(
                        contract_title=contract_title,
                        contract_type_code=self._contract_type_combo.currentData() or "other",
                        currency_code=currency_code,
                        base_contract_amount=base_amount,
                        start_date=start_date,
                        planned_end_date=planned_end_date,
                        billing_basis_code=billing_basis or None,
                        retention_percent=retention,
                        reference_number=self._reference_number_edit.text().strip() or None,
                        description=self._description_edit.toPlainText().strip() or None,
                    ),
                )
        except (ValidationError, ConflictError) as exc:
            self._set_error(str(exc))
            return
        except NotFoundError as exc:
            show_error(self, "Contract Not Found", str(exc))
            return

        self.accept()
