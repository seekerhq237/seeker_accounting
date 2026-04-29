"""Step 1 — Identity (code, name, type, description)."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.wizards.new_item import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


_TYPE_OPTIONS = [
    ("stock", "Stock — tracked inventory"),
    ("non_stock", "Non-stock — purchased but not tracked"),
    ("service", "Service — labour, billable hours, etc."),
]


class IdentityStep(WizardStep):
    key = "identity"
    title = "Identity"
    subtitle = "Item code, name, and type."

    def __init__(self) -> None:
        super().__init__()
        self._code: QLineEdit | None = None
        self._name: QLineEdit | None = None
        self._type: QComboBox | None = None
        self._description: QTextEdit | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        form = QFormLayout()

        self._code = QLineEdit(root)
        self._code.setPlaceholderText("e.g. ITM-001")
        self._code.setMaxLength(40)
        form.addRow(QLabel("Item code:", root), self._code)

        self._name = QLineEdit(root)
        self._name.setMaxLength(160)
        form.addRow(QLabel("Item name:", root), self._name)

        self._type = QComboBox(root)
        for code, label in _TYPE_OPTIONS:
            self._type.addItem(label, code)
        form.addRow(QLabel("Item type:", root), self._type)

        self._description = QTextEdit(root)
        self._description.setMaximumHeight(60)
        form.addRow(QLabel("Description:", root), self._description)

        outer.addLayout(form)
        outer.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._code is not None and state.get(K.KEY_ITEM_CODE):
            self._code.setText(str(state[K.KEY_ITEM_CODE]))
        if self._name is not None and state.get(K.KEY_ITEM_NAME):
            self._name.setText(str(state[K.KEY_ITEM_NAME]))
        if self._type is not None:
            prior = state.get(K.KEY_ITEM_TYPE_CODE)
            if isinstance(prior, str):
                idx = self._type.findData(prior)
                if idx >= 0:
                    self._type.setCurrentIndex(idx)
        if self._description is not None and state.get(K.KEY_DESCRIPTION):
            self._description.setPlainText(str(state[K.KEY_DESCRIPTION]))

    def write_back(self, state: WizardState) -> None:
        if self._code is not None:
            state[K.KEY_ITEM_CODE] = self._code.text().strip()
        if self._name is not None:
            state[K.KEY_ITEM_NAME] = self._name.text().strip()
        if self._type is not None:
            data = self._type.currentData()
            state[K.KEY_ITEM_TYPE_CODE] = str(data) if data else "stock"
        if self._description is not None:
            state[K.KEY_DESCRIPTION] = self._description.toPlainText().strip() or None

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        if not state.get(K.KEY_ITEM_CODE):
            return StepValidationResult.fail("Item code is required.")
        if not state.get(K.KEY_ITEM_NAME):
            return StepValidationResult.fail("Item name is required.")
        if not state.get(K.KEY_ITEM_TYPE_CODE):
            return StepValidationResult.fail("Item type is required.")
        return StepValidationResult.ok()

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        return f"{state.get(K.KEY_ITEM_CODE) or '(no code)'} \u2014 {state.get(K.KEY_ITEM_NAME) or ''}".strip()
