"""Step 2 — Contact and address."""
from __future__ import annotations

from PySide6.QtWidgets import (
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


class ContactStep(WizardStep):
    key = "contact"
    title = "Contact"
    subtitle = "Phone, email, address (all optional)."

    def __init__(self) -> None:
        super().__init__()
        self._fields: dict[str, QLineEdit] = {}

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        form = QFormLayout()

        layout_spec = [
            (K.KEY_PHONE, "Phone:", "+1 555-555-5555"),
            (K.KEY_EMAIL, "Email:", "ap@example.com"),
            (K.KEY_ADDRESS_LINE_1, "Address line 1:", ""),
            (K.KEY_ADDRESS_LINE_2, "Address line 2:", ""),
            (K.KEY_CITY, "City:", ""),
            (K.KEY_REGION, "Region/State:", ""),
            (K.KEY_COUNTRY_CODE, "Country code:", "US"),
        ]
        for key, label, placeholder in layout_spec:
            edit = QLineEdit(root)
            edit.setPlaceholderText(placeholder)
            if key == K.KEY_COUNTRY_CODE:
                edit.setMaxLength(3)
            self._fields[key] = edit
            form.addRow(QLabel(label, root), edit)
        outer.addLayout(form)
        outer.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        for key, widget in self._fields.items():
            val = state.get(key)
            if val:
                widget.setText(str(val))

    def write_back(self, state: WizardState) -> None:
        for key, widget in self._fields.items():
            text = widget.text().strip()
            if key == K.KEY_COUNTRY_CODE:
                text = text.upper()
            state[key] = text or None

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        email = state.get(K.KEY_EMAIL)
        if email and "@" not in str(email):
            return StepValidationResult.fail("Email looks invalid.")
        cc = state.get(K.KEY_COUNTRY_CODE)
        if cc and not (2 <= len(str(cc)) <= 3):
            return StepValidationResult.fail("Country code should be 2 or 3 letters.")
        return StepValidationResult.ok()

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        bits = [
            x for x in (state.get(K.KEY_CITY), state.get(K.KEY_COUNTRY_CODE)) if x
        ]
        return ", ".join(str(b) for b in bits) if bits else "No address provided."
