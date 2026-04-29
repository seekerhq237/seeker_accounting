"""Step 1 — Identity: username, display name, email, password."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.wizards.user_provisioning import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class IdentityStep(WizardStep):
    key = "identity"
    title = "Identity"
    subtitle = "Username, display name, email, and an initial password."

    def __init__(self) -> None:
        super().__init__()
        self._username: QLineEdit | None = None
        self._display_name: QLineEdit | None = None
        self._email: QLineEdit | None = None
        self._password: QLineEdit | None = None
        self._confirm: QLineEdit | None = None
        self._must_change: QCheckBox | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        form = QFormLayout()

        self._username = QLineEdit(root)
        self._username.setMaxLength(60)
        self._username.setPlaceholderText("e.g. j.smith")
        form.addRow(QLabel("Username:", root), self._username)

        self._display_name = QLineEdit(root)
        self._display_name.setMaxLength(120)
        self._display_name.setPlaceholderText("e.g. Jane Smith")
        form.addRow(QLabel("Display name:", root), self._display_name)

        self._email = QLineEdit(root)
        self._email.setMaxLength(200)
        self._email.setPlaceholderText("optional")
        form.addRow(QLabel("Email:", root), self._email)

        self._password = QLineEdit(root)
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._password.setMaxLength(120)
        form.addRow(QLabel("Initial password:", root), self._password)

        self._confirm = QLineEdit(root)
        self._confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self._confirm.setMaxLength(120)
        form.addRow(QLabel("Confirm password:", root), self._confirm)

        self._must_change = QCheckBox("Require password change on first login", root)
        self._must_change.setChecked(True)
        form.addRow(QLabel("", root), self._must_change)

        outer.addLayout(form)
        outer.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._username is not None and state.get(K.KEY_USERNAME):
            self._username.setText(str(state[K.KEY_USERNAME]))
        if self._display_name is not None and state.get(K.KEY_DISPLAY_NAME):
            self._display_name.setText(str(state[K.KEY_DISPLAY_NAME]))
        if self._email is not None and state.get(K.KEY_EMAIL):
            self._email.setText(str(state[K.KEY_EMAIL]))
        if self._password is not None and state.get(K.KEY_PASSWORD):
            self._password.setText(str(state[K.KEY_PASSWORD]))
        if self._confirm is not None and state.get(K.KEY_CONFIRM_PASSWORD):
            self._confirm.setText(str(state[K.KEY_CONFIRM_PASSWORD]))
        if self._must_change is not None:
            v = state.get(K.KEY_MUST_CHANGE_PASSWORD)
            self._must_change.setChecked(True if v is None else bool(v))

    def write_back(self, state: WizardState) -> None:
        if self._username is not None:
            state[K.KEY_USERNAME] = self._username.text().strip() or None
        if self._display_name is not None:
            state[K.KEY_DISPLAY_NAME] = self._display_name.text().strip() or None
        if self._email is not None:
            state[K.KEY_EMAIL] = self._email.text().strip() or None
        if self._password is not None:
            state[K.KEY_PASSWORD] = self._password.text() or None
        if self._confirm is not None:
            state[K.KEY_CONFIRM_PASSWORD] = self._confirm.text() or None
        if self._must_change is not None:
            state[K.KEY_MUST_CHANGE_PASSWORD] = bool(self._must_change.isChecked())

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        if not state.get(K.KEY_USERNAME):
            return StepValidationResult.fail("Username is required.")
        if not state.get(K.KEY_DISPLAY_NAME):
            return StepValidationResult.fail("Display name is required.")
        password = state.get(K.KEY_PASSWORD) or ""
        if not password:
            return StepValidationResult.fail("Initial password is required.")
        if len(password) < 8:
            return StepValidationResult.fail("Password must be at least 8 characters.")
        if state.get(K.KEY_CONFIRM_PASSWORD) != password:
            return StepValidationResult.fail("Password and confirmation do not match.")
        email = state.get(K.KEY_EMAIL)
        if email and "@" not in email:
            return StepValidationResult.fail("Email looks invalid.")
        return StepValidationResult.ok()

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        u = state.get(K.KEY_USERNAME)
        n = state.get(K.KEY_DISPLAY_NAME)
        if u and n:
            return f"{u} \u2014 {n}"
        return None
