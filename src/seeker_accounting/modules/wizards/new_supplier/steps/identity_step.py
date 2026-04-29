"""Step 1 — Identity (code, names, group)."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.wizards.new_supplier import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class IdentityStep(WizardStep):
    key = "identity"
    title = "Identity"
    subtitle = "Supplier code, display name, and group."

    def __init__(self) -> None:
        super().__init__()
        self._code: QLineEdit | None = None
        self._display: QLineEdit | None = None
        self._legal: QLineEdit | None = None
        self._group: QComboBox | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        form = QFormLayout()
        self._code = QLineEdit(root)
        self._code.setPlaceholderText("e.g. SUP-001")
        self._code.setMaxLength(40)
        form.addRow(QLabel("Supplier code:", root), self._code)

        self._display = QLineEdit(root)
        self._display.setMaxLength(120)
        form.addRow(QLabel("Display name:", root), self._display)

        self._legal = QLineEdit(root)
        self._legal.setMaxLength(160)
        form.addRow(QLabel("Legal name:", root), self._legal)

        self._group = QComboBox(root)
        form.addRow(QLabel("Group:", root), self._group)
        outer.addLayout(form)
        outer.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._group is not None and self._group.count() == 0:
            company_id = context.require_company_id()
            self._group.addItem("(none)", None)
            for g in context.service_registry.supplier_service.list_supplier_groups(
                company_id, active_only=True
            ):
                self._group.addItem(f"{g.code} \u2014 {g.name}", g.id)
            prior = state.get(K.KEY_SUPPLIER_GROUP_ID)
            if isinstance(prior, int):
                idx = self._group.findData(prior)
                if idx >= 0:
                    self._group.setCurrentIndex(idx)
        if self._code is not None and state.get(K.KEY_SUPPLIER_CODE):
            self._code.setText(str(state[K.KEY_SUPPLIER_CODE]))
        if self._display is not None and state.get(K.KEY_DISPLAY_NAME):
            self._display.setText(str(state[K.KEY_DISPLAY_NAME]))
        if self._legal is not None and state.get(K.KEY_LEGAL_NAME):
            self._legal.setText(str(state[K.KEY_LEGAL_NAME]))

    def write_back(self, state: WizardState) -> None:
        if self._code is not None:
            state[K.KEY_SUPPLIER_CODE] = self._code.text().strip()
        if self._display is not None:
            state[K.KEY_DISPLAY_NAME] = self._display.text().strip()
        if self._legal is not None:
            state[K.KEY_LEGAL_NAME] = self._legal.text().strip() or None
        if self._group is not None:
            data = self._group.currentData()
            state[K.KEY_SUPPLIER_GROUP_ID] = int(data) if isinstance(data, int) else None

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        if not state.get(K.KEY_SUPPLIER_CODE):
            return StepValidationResult.fail("Supplier code is required.")
        if not state.get(K.KEY_DISPLAY_NAME):
            return StepValidationResult.fail("Display name is required.")
        return StepValidationResult.ok()

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        return f"{state.get(K.KEY_SUPPLIER_CODE) or '(no code)'} \u2014 {state.get(K.KEY_DISPLAY_NAME) or ''}".strip()
