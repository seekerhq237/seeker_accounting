"""Step 1 — Pick mode (create vs update) and document type."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFormLayout,
    QLabel,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.wizards.document_numbering import state_keys as K
from seeker_accounting.modules.wizards.document_numbering.catalog import (
    VALID_DOCUMENT_TYPES,
)
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class PickStep(WizardStep):
    key = "pick"
    title = "Pick"
    subtitle = "Create a new sequence or edit an existing one."

    def __init__(self) -> None:
        super().__init__()
        self._create_radio: QRadioButton | None = None
        self._update_radio: QRadioButton | None = None
        self._group: QButtonGroup | None = None
        self._new_combo: QComboBox | None = None
        self._existing_combo: QComboBox | None = None
        self._existing_doc_types: set[str] = set()

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        self._create_radio = QRadioButton("Create a new sequence", root)
        self._update_radio = QRadioButton("Update an existing sequence", root)
        self._group = QButtonGroup(root)
        self._group.addButton(self._create_radio, 0)
        self._group.addButton(self._update_radio, 1)
        self._create_radio.setChecked(True)
        outer.addWidget(self._create_radio)
        outer.addWidget(self._update_radio)

        form = QFormLayout()
        self._new_combo = QComboBox(root)
        form.addRow(QLabel("Document type (new):", root), self._new_combo)
        self._existing_combo = QComboBox(root)
        form.addRow(QLabel("Existing sequence:", root), self._existing_combo)
        outer.addLayout(form)

        self._create_radio.toggled.connect(self._on_mode_changed)
        outer.addStretch(1)
        return root

    def _on_mode_changed(self, _checked: bool) -> None:
        if self._new_combo is not None and self._create_radio is not None:
            self._new_combo.setEnabled(self._create_radio.isChecked())
        if self._existing_combo is not None and self._update_radio is not None:
            self._existing_combo.setEnabled(self._update_radio.isChecked())

    def load(self, context: WizardContext, state: WizardState) -> None:
        company_id = context.require_company_id()
        existing = context.service_registry.numbering_setup_service.list_document_sequences(
            company_id, active_only=False
        )
        self._existing_doc_types = {row.document_type_code for row in existing}

        if self._new_combo is not None and self._new_combo.count() == 0:
            for code, label in VALID_DOCUMENT_TYPES:
                marker = " (already configured)" if code in self._existing_doc_types else ""
                self._new_combo.addItem(f"{label}{marker}", code)
        if self._existing_combo is not None and self._existing_combo.count() == 0:
            if existing:
                for row in existing:
                    label = next((lbl for c, lbl in VALID_DOCUMENT_TYPES if c == row.document_type_code), row.document_type_code)
                    formatted = (row.prefix or "") + str(row.next_number).zfill(row.padding_width) + (row.suffix or "")
                    self._existing_combo.addItem(
                        f"{label} \u2014 next: {formatted}", row.id
                    )
            else:
                self._existing_combo.addItem("(no sequences configured)", None)

        # Restore prior choice if any
        prior_mode = state.get(K.KEY_MODE)
        if prior_mode == "update" and self._update_radio is not None:
            self._update_radio.setChecked(True)
        else:
            if self._create_radio is not None:
                self._create_radio.setChecked(True)
        prior_doc = state.get(K.KEY_DOCUMENT_TYPE_CODE)
        if isinstance(prior_doc, str) and self._new_combo is not None:
            idx = self._new_combo.findData(prior_doc)
            if idx >= 0:
                self._new_combo.setCurrentIndex(idx)
        prior_seq = state.get(K.KEY_SEQUENCE_ID)
        if isinstance(prior_seq, int) and self._existing_combo is not None:
            idx = self._existing_combo.findData(prior_seq)
            if idx >= 0:
                self._existing_combo.setCurrentIndex(idx)
        self._on_mode_changed(True)

    def write_back(self, state: WizardState) -> None:
        if self._create_radio is not None and self._create_radio.isChecked():
            state[K.KEY_MODE] = "create"
            if self._new_combo is not None:
                data = self._new_combo.currentData()
                state[K.KEY_DOCUMENT_TYPE_CODE] = str(data) if data else None
            state[K.KEY_SEQUENCE_ID] = None
        else:
            state[K.KEY_MODE] = "update"
            if self._existing_combo is not None:
                data = self._existing_combo.currentData()
                state[K.KEY_SEQUENCE_ID] = int(data) if isinstance(data, int) else None

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        mode = state.get(K.KEY_MODE)
        if mode == "create":
            doc = state.get(K.KEY_DOCUMENT_TYPE_CODE)
            if not doc:
                return StepValidationResult.fail("Pick a document type.")
            if doc in self._existing_doc_types:
                return StepValidationResult.fail(
                    "That document type is already configured. Switch to 'Update' mode."
                )
        elif mode == "update":
            if not isinstance(state.get(K.KEY_SEQUENCE_ID), int):
                return StepValidationResult.fail("Pick an existing sequence to update.")
        return StepValidationResult.ok()

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        mode = state.get(K.KEY_MODE)
        if mode == "create":
            return f"Create sequence for {state.get(K.KEY_DOCUMENT_TYPE_CODE) or '?'}"
        if mode == "update":
            sid = state.get(K.KEY_SEQUENCE_ID)
            return f"Update sequence #{sid}" if sid else None
        return None
