"""Step 2 — Configure prefix, next number, padding, reset frequency."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.wizards.document_numbering import state_keys as K
from seeker_accounting.modules.wizards.document_numbering.catalog import (
    RESET_FREQUENCY_OPTIONS,
)
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class ConfigureStep(WizardStep):
    key = "configure"
    title = "Configure"
    subtitle = "Prefix, next number, padding, reset frequency."

    def __init__(self) -> None:
        super().__init__()
        self._prefix: QLineEdit | None = None
        self._suffix: QLineEdit | None = None
        self._next_number: QSpinBox | None = None
        self._padding: QSpinBox | None = None
        self._reset: QComboBox | None = None
        self._preview_label: QLabel | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        form = QFormLayout()

        self._prefix = QLineEdit(root)
        self._prefix.setPlaceholderText("e.g. INV-")
        self._prefix.setMaxLength(16)
        form.addRow(QLabel("Prefix:", root), self._prefix)

        self._suffix = QLineEdit(root)
        self._suffix.setMaxLength(16)
        form.addRow(QLabel("Suffix:", root), self._suffix)

        self._next_number = QSpinBox(root)
        self._next_number.setRange(1, 9_999_999)
        self._next_number.setValue(1)
        form.addRow(QLabel("Next number:", root), self._next_number)

        self._padding = QSpinBox(root)
        self._padding.setRange(1, 12)
        self._padding.setValue(4)
        form.addRow(QLabel("Padding width:", root), self._padding)

        self._reset = QComboBox(root)
        for code, label in RESET_FREQUENCY_OPTIONS:
            self._reset.addItem(label, code)
        form.addRow(QLabel("Reset frequency:", root), self._reset)

        outer.addLayout(form)

        self._preview_label = QLabel(root)
        self._preview_label.setStyleSheet("font-weight: 600;")
        outer.addWidget(self._preview_label)

        outer.addStretch(1)

        for w in (self._prefix, self._suffix):
            w.textChanged.connect(self._refresh_preview)
        for sp in (self._next_number, self._padding):
            sp.valueChanged.connect(self._refresh_preview)
        return root

    def _refresh_preview(self) -> None:
        if self._preview_label is None:
            return
        prefix = self._prefix.text() if self._prefix else ""
        suffix = self._suffix.text() if self._suffix else ""
        nn = self._next_number.value() if self._next_number else 1
        pad = self._padding.value() if self._padding else 4
        self._preview_label.setText(f"Next number will look like: {prefix}{str(nn).zfill(pad)}{suffix}")

    def load(self, context: WizardContext, state: WizardState) -> None:
        # Prefill from existing sequence in update mode
        if state.get(K.KEY_MODE) == "update" and self._prefix is not None and not state.get(K.KEY_PREFIX):
            sid = state.get(K.KEY_SEQUENCE_ID)
            if isinstance(sid, int):
                company_id = context.require_company_id()
                seq = context.service_registry.numbering_setup_service.get_document_sequence(company_id, sid)
                state[K.KEY_DOCUMENT_TYPE_CODE] = seq.document_type_code
                state[K.KEY_PREFIX] = seq.prefix
                state[K.KEY_SUFFIX] = seq.suffix
                state[K.KEY_NEXT_NUMBER] = seq.next_number
                state[K.KEY_PADDING_WIDTH] = seq.padding_width
                state[K.KEY_RESET_FREQUENCY_CODE] = seq.reset_frequency_code
        if self._prefix is not None:
            self._prefix.setText(str(state.get(K.KEY_PREFIX) or ""))
        if self._suffix is not None:
            self._suffix.setText(str(state.get(K.KEY_SUFFIX) or ""))
        if self._next_number is not None and isinstance(state.get(K.KEY_NEXT_NUMBER), int):
            self._next_number.setValue(int(state[K.KEY_NEXT_NUMBER]))
        if self._padding is not None and isinstance(state.get(K.KEY_PADDING_WIDTH), int):
            self._padding.setValue(int(state[K.KEY_PADDING_WIDTH]))
        if self._reset is not None:
            prior = state.get(K.KEY_RESET_FREQUENCY_CODE)
            idx = self._reset.findData(prior)
            if idx >= 0:
                self._reset.setCurrentIndex(idx)
        self._refresh_preview()

    def write_back(self, state: WizardState) -> None:
        if self._prefix is not None:
            state[K.KEY_PREFIX] = self._prefix.text() or None
        if self._suffix is not None:
            state[K.KEY_SUFFIX] = self._suffix.text() or None
        if self._next_number is not None:
            state[K.KEY_NEXT_NUMBER] = int(self._next_number.value())
        if self._padding is not None:
            state[K.KEY_PADDING_WIDTH] = int(self._padding.value())
        if self._reset is not None:
            data = self._reset.currentData()
            state[K.KEY_RESET_FREQUENCY_CODE] = str(data) if data else None

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        if not isinstance(state.get(K.KEY_NEXT_NUMBER), int) or int(state[K.KEY_NEXT_NUMBER]) < 1:
            return StepValidationResult.fail("Next number must be 1 or greater.")
        if not isinstance(state.get(K.KEY_PADDING_WIDTH), int) or int(state[K.KEY_PADDING_WIDTH]) < 1:
            return StepValidationResult.fail("Padding width must be 1 or greater.")
        return StepValidationResult.ok()

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        prefix = state.get(K.KEY_PREFIX) or ""
        suffix = state.get(K.KEY_SUFFIX) or ""
        nn = int(state.get(K.KEY_NEXT_NUMBER) or 1)
        pad = int(state.get(K.KEY_PADDING_WIDTH) or 4)
        return f"{prefix}{str(nn).zfill(pad)}{suffix}"
