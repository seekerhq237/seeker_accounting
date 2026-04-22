from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.accounting.reference_data.dto.numbering_dto import (
    CreateDocumentSequenceCommand,
    DocumentSequenceDTO,
    UpdateDocumentSequenceCommand,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.forms import create_field_block, create_label_value_row
from seeker_accounting.shared.ui.message_boxes import show_error

_DOCUMENT_TYPE_CODES: tuple[str, ...] = (
    "SALES_INVOICE",
    "PURCHASE_BILL",
    "CUSTOMER_RECEIPT",
    "SUPPLIER_PAYMENT",
    "JOURNAL_ENTRY",
)

_RESET_FREQUENCY_CODES: tuple[str, ...] = (
    "",
    "MONTHLY",
    "QUARTERLY",
    "YEARLY",
)


class DocumentSequenceDialog(BaseDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        sequence_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._sequence_id = sequence_id
        self._saved_sequence: DocumentSequenceDTO | None = None

        title = "New Document Sequence" if sequence_id is None else "Edit Document Sequence"
        super().__init__(title, parent, help_key="dialog.document_sequence")
        self.setObjectName("DocumentSequenceDialog")
        self.resize(520, 0)

        self.body_layout.addWidget(create_label_value_row("Company", company_name, self))

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        self.body_layout.addWidget(self._error_label)

        self.body_layout.addWidget(self._build_sequence_section())

        self.button_box.setStandardButtons(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        self.button_box.accepted.connect(self._handle_submit)

        self._save_button = self.button_box.button(QDialogButtonBox.StandardButton.Save)
        if self._save_button is not None:
            self._save_button.setText("Create Sequence" if sequence_id is None else "Save Changes")
            self._save_button.setProperty("variant", "primary")

        cancel_button = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button is not None:
            cancel_button.setProperty("variant", "secondary")

        self._prepare_editable_combo(
            self._document_type_combo,
            _DOCUMENT_TYPE_CODES,
            "Enter or select document type",
        )
        self._prepare_editable_combo(
            self._reset_frequency_combo,
            _RESET_FREQUENCY_CODES,
            "Optional reset frequency",
        )

        if self._sequence_id is not None:
            self._load_sequence()

        self.adjustSize()

    @property
    def saved_sequence(self) -> DocumentSequenceDTO | None:
        return self._saved_sequence

    @classmethod
    def create_sequence(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> DocumentSequenceDTO | None:
        dialog = cls(
            service_registry=service_registry,
            company_id=company_id,
            company_name=company_name,
            parent=parent,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_sequence
        return None

    @classmethod
    def create_sequence_for_type(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        document_type_code: str,
        parent: QWidget | None = None,
    ) -> DocumentSequenceDTO | None:
        """Open create dialog with document type pre-selected and locked."""
        dialog = cls(
            service_registry=service_registry,
            company_id=company_id,
            company_name=company_name,
            parent=parent,
        )
        normalized = document_type_code.strip().upper()
        index = dialog._document_type_combo.findText(normalized)
        if index >= 0:
            dialog._document_type_combo.setCurrentIndex(index)
        else:
            dialog._document_type_combo.setEditText(normalized)
        dialog._document_type_combo.setEnabled(False)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_sequence
        return None

    @classmethod
    def edit_sequence(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        sequence_id: int,
        parent: QWidget | None = None,
    ) -> DocumentSequenceDTO | None:
        dialog = cls(
            service_registry=service_registry,
            company_id=company_id,
            company_name=company_name,
            sequence_id=sequence_id,
            parent=parent,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_sequence
        return None

    def _build_sequence_section(self) -> QWidget:
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

        self._document_type_combo = QComboBox(card)
        self._document_type_combo.setEditable(True)
        grid.addWidget(create_field_block("Document Type", self._document_type_combo), 0, 0)

        self._reset_frequency_combo = QComboBox(card)
        self._reset_frequency_combo.setEditable(True)
        grid.addWidget(create_field_block("Reset Frequency", self._reset_frequency_combo), 0, 1)

        self._prefix_edit = QLineEdit(card)
        self._prefix_edit.setPlaceholderText("INV-")
        grid.addWidget(create_field_block("Prefix", self._prefix_edit), 1, 0)

        self._suffix_edit = QLineEdit(card)
        self._suffix_edit.setPlaceholderText("-A")
        grid.addWidget(create_field_block("Suffix", self._suffix_edit), 1, 1)

        self._next_number_spin = QSpinBox(card)
        self._next_number_spin.setRange(1, 999_999_999)
        self._next_number_spin.setAccelerated(True)
        grid.addWidget(create_field_block("Next Number", self._next_number_spin), 2, 0)

        self._padding_width_spin = QSpinBox(card)
        self._padding_width_spin.setRange(0, 12)
        self._padding_width_spin.setAccelerated(True)
        grid.addWidget(create_field_block("Padding Width", self._padding_width_spin), 2, 1)

        layout.addLayout(grid)
        return card

    def _prepare_editable_combo(self, combo_box: QComboBox, codes: tuple[str, ...], placeholder: str) -> None:
        combo_box.clear()
        for code in codes:
            combo_box.addItem(code)
        combo_box.setCurrentIndex(0)
        line_edit = combo_box.lineEdit()
        if line_edit is not None:
            line_edit.setPlaceholderText(placeholder)

    def _selected_code(self, combo_box: QComboBox) -> str:
        return combo_box.currentText().strip().upper()

    def _normalize_optional_text(self, value: str) -> str | None:
        normalized = value.strip()
        return normalized or None

    def _load_sequence(self) -> None:
        try:
            sequence = self._service_registry.numbering_setup_service.get_document_sequence(
                self._company_id,
                self._sequence_id or 0,
            )
        except NotFoundError as exc:
            show_error(self, "Document Sequence Not Found", str(exc))
            self.reject()
            return

        self._document_type_combo.setEditText(sequence.document_type_code)
        self._reset_frequency_combo.setEditText(sequence.reset_frequency_code or "")
        self._prefix_edit.setText(sequence.prefix or "")
        self._suffix_edit.setText(sequence.suffix or "")
        self._next_number_spin.setValue(sequence.next_number)
        self._padding_width_spin.setValue(sequence.padding_width)

    def _set_error(self, message: str | None) -> None:
        if not message:
            self._error_label.clear()
            self._error_label.hide()
            return

        self._error_label.setText(message)
        self._error_label.show()

    def _handle_submit(self) -> None:
        self._set_error(None)

        document_type_code = self._selected_code(self._document_type_combo)
        if not document_type_code:
            self._set_error("Document type is required.")
            self._document_type_combo.setFocus(Qt.FocusReason.OtherFocusReason)
            return

        if self._sequence_id is None:
            command = CreateDocumentSequenceCommand(
                document_type_code=document_type_code,
                prefix=self._normalize_optional_text(self._prefix_edit.text()),
                suffix=self._normalize_optional_text(self._suffix_edit.text()),
                next_number=self._next_number_spin.value(),
                padding_width=self._padding_width_spin.value(),
                reset_frequency_code=self._normalize_optional_text(self._reset_frequency_combo.currentText()),
            )
            save_operation = lambda: self._service_registry.numbering_setup_service.create_document_sequence(
                self._company_id,
                command,
            )
        else:
            command = UpdateDocumentSequenceCommand(
                document_type_code=document_type_code,
                prefix=self._normalize_optional_text(self._prefix_edit.text()),
                suffix=self._normalize_optional_text(self._suffix_edit.text()),
                next_number=self._next_number_spin.value(),
                padding_width=self._padding_width_spin.value(),
                reset_frequency_code=self._normalize_optional_text(self._reset_frequency_combo.currentText()),
            )
            save_operation = lambda: self._service_registry.numbering_setup_service.update_document_sequence(
                self._company_id,
                self._sequence_id,
                command,
            )

        try:
            self._saved_sequence = save_operation()
        except (ValidationError, ConflictError) as exc:
            self._set_error(str(exc))
            return
        except NotFoundError as exc:
            show_error(self, "Document Sequence Not Found", str(exc))
            return

        self.accept()

