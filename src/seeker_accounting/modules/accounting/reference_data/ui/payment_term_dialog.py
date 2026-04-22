from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.accounting.reference_data.dto.reference_data_dto import (
    CreatePaymentTermCommand,
    PaymentTermDTO,
    UpdatePaymentTermCommand,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.forms import create_field_block, create_label_value_row
from seeker_accounting.shared.ui.message_boxes import show_error


class PaymentTermDialog(BaseDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        payment_term_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._payment_term_id = payment_term_id
        self._saved_payment_term: PaymentTermDTO | None = None

        title = "New Payment Term" if payment_term_id is None else "Edit Payment Term"
        super().__init__(title, parent, help_key="dialog.payment_term")
        self.setObjectName("PaymentTermDialog")
        self.resize(480, 0)

        self.body_layout.addWidget(create_label_value_row("Company", company_name, self))

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        self.body_layout.addWidget(self._error_label)

        self.body_layout.addWidget(self._build_definition_section())

        self.button_box.setStandardButtons(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        self.button_box.accepted.connect(self._handle_submit)

        self._save_button = self.button_box.button(QDialogButtonBox.StandardButton.Save)
        if self._save_button is not None:
            self._save_button.setText("Create Payment Term" if payment_term_id is None else "Save Changes")
            self._save_button.setProperty("variant", "primary")

        cancel_button = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button is not None:
            cancel_button.setProperty("variant", "secondary")

        if self._payment_term_id is not None:
            self._load_payment_term()
        else:
            self._suggest_code()

        self.adjustSize()

    @property
    def saved_payment_term(self) -> PaymentTermDTO | None:
        return self._saved_payment_term

    @classmethod
    def create_payment_term(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> PaymentTermDTO | None:
        dialog = cls(
            service_registry=service_registry,
            company_id=company_id,
            company_name=company_name,
            parent=parent,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_payment_term
        return None

    @classmethod
    def edit_payment_term(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        payment_term_id: int,
        parent: QWidget | None = None,
    ) -> PaymentTermDTO | None:
        dialog = cls(
            service_registry=service_registry,
            company_id=company_id,
            company_name=company_name,
            payment_term_id=payment_term_id,
            parent=parent,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_payment_term
        return None

    def _build_definition_section(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(6)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)

        self._code_edit = QLineEdit(card)
        self._code_edit.setPlaceholderText("NET30")
        grid.addWidget(create_field_block("Code", self._code_edit), 0, 0)

        self._name_edit = QLineEdit(card)
        self._name_edit.setPlaceholderText("Net 30")
        grid.addWidget(create_field_block("Name", self._name_edit), 0, 1)

        self._days_due_spin = QSpinBox(card)
        self._days_due_spin.setRange(0, 3650)
        self._days_due_spin.setAccelerated(True)
        grid.addWidget(create_field_block("Days Due", self._days_due_spin), 1, 0)

        self._description_edit = QPlainTextEdit(card)
        self._description_edit.setPlaceholderText("Optional note for operators")
        self._description_edit.setFixedHeight(84)
        grid.addWidget(create_field_block("Description", self._description_edit), 1, 1)

        layout.addLayout(grid)
        return card

    def _suggest_code(self) -> None:
        try:
            code = self._service_registry.code_suggestion_service.suggest("payment_term", self._company_id)
            self._code_edit.setText(code)
        except Exception:
            pass

    def _load_payment_term(self) -> None:
        try:
            payment_term = self._service_registry.reference_data_service.get_payment_term(
                self._company_id,
                self._payment_term_id or 0,
            )
        except NotFoundError as exc:
            show_error(self, "Payment Term Not Found", str(exc))
            self.reject()
            return

        self._code_edit.setText(payment_term.code)
        self._name_edit.setText(payment_term.name)
        self._days_due_spin.setValue(payment_term.days_due)
        self._description_edit.setPlainText(payment_term.description or "")

    def _set_error(self, message: str | None) -> None:
        if not message:
            self._error_label.clear()
            self._error_label.hide()
            return

        self._error_label.setText(message)
        self._error_label.show()

    def _handle_submit(self) -> None:
        self._set_error(None)

        code = self._code_edit.text().strip()
        name = self._name_edit.text().strip()
        description = self._description_edit.toPlainText().strip() or None

        if not code:
            self._set_error("Code is required.")
            self._code_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        if not name:
            self._set_error("Name is required.")
            self._name_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return

        if self._payment_term_id is None:
            command = CreatePaymentTermCommand(
                code=code,
                name=name,
                days_due=self._days_due_spin.value(),
                description=description,
            )
            save_operation = lambda: self._service_registry.reference_data_service.create_payment_term(
                self._company_id,
                command,
            )
        else:
            command = UpdatePaymentTermCommand(
                code=code,
                name=name,
                days_due=self._days_due_spin.value(),
                description=description,
            )
            save_operation = lambda: self._service_registry.reference_data_service.update_payment_term(
                self._company_id,
                self._payment_term_id,
                command,
            )

        try:
            self._saved_payment_term = save_operation()
        except (ValidationError, ConflictError) as exc:
            self._set_error(str(exc))
            return
        except NotFoundError as exc:
            show_error(self, "Payment Term Not Found", str(exc))
            return

        self.accept()

