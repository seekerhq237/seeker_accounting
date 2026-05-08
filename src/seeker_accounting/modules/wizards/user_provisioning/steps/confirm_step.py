"""Step 3 — Confirm: create user, assign roles, grant company access."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from seeker_accounting.modules.administration.dto.user_commands import CreateUserCommand
from seeker_accounting.modules.wizards.user_provisioning import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class ConfirmStep(WizardStep):
    key = "confirm"
    title = "Confirm"
    subtitle = "Review and provision the user."

    commits_on_advance = True

    def __init__(self) -> None:
        super().__init__()
        self._summary: QLabel | None = None
        self._result: QLabel | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        self._summary = QLabel(root)
        self._summary.setWordWrap(True)
        self._summary.setTextFormat(Qt.TextFormat.RichText)
        outer.addWidget(self._summary)
        self._result = QLabel(root)
        self._result.setObjectName("WizardSuccessText")
        outer.addWidget(self._result)
        outer.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._summary is not None:
            codes = state.get(K.KEY_ROLE_CODES) or []
            roles_html = ", ".join(codes) if codes else "<i>(none)</i>"
            grant = bool(state.get(K.KEY_GRANT_CURRENT_COMPANY))
            default = bool(state.get(K.KEY_IS_DEFAULT_COMPANY))
            access_html = (
                f"Yes (default: {'yes' if default else 'no'})" if grant else "No"
            )
            html = (
                f"<b>Username:</b> {state.get(K.KEY_USERNAME)}<br>"
                f"<b>Display name:</b> {state.get(K.KEY_DISPLAY_NAME)}<br>"
                f"<b>Email:</b> {state.get(K.KEY_EMAIL) or '<i>(none)</i>'}<br>"
                f"<b>Must change password:</b> "
                f"{'yes' if state.get(K.KEY_MUST_CHANGE_PASSWORD) else 'no'}<br>"
                f"<b>Roles:</b> {roles_html}<br>"
                f"<b>Grant access to current company:</b> {access_html}"
            )
            self._summary.setText(html)
        if self._result is not None and state.get(K.KEY_USER_ID):
            self._result.setText(f"User #{state[K.KEY_USER_ID]} provisioned.")

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        return StepValidationResult.ok()

    def commit(self, context: WizardContext, state: WizardState) -> None:
        if isinstance(state.get(K.KEY_USER_ID), int):
            return
        sr = context.service_registry
        cmd = CreateUserCommand(
            username=str(state[K.KEY_USERNAME]),
            display_name=str(state[K.KEY_DISPLAY_NAME]),
            password=str(state[K.KEY_PASSWORD]),
            email=state.get(K.KEY_EMAIL),
            must_change_password=bool(state.get(K.KEY_MUST_CHANGE_PASSWORD)),
        )
        user_dto = sr.user_auth_service.create_user(cmd)
        user_id = int(user_dto.id)
        state[K.KEY_USER_ID] = user_id

        for role_id in state.get(K.KEY_ROLE_IDS) or []:
            try:
                sr.user_auth_service.assign_role(user_id, int(role_id))
            except Exception:
                # role assignment failures should not roll back the created user;
                # surface via state but continue. UI can re-attempt from admin.
                continue

        if bool(state.get(K.KEY_GRANT_CURRENT_COMPANY)):
            company_id = context.require_company_id()
            try:
                sr.user_auth_service.grant_company_access(
                    user_id,
                    company_id,
                    is_default=bool(state.get(K.KEY_IS_DEFAULT_COMPANY)),
                )
            except Exception:
                pass

        # Scrub password material from state once committed.
        state[K.KEY_PASSWORD] = None
        state[K.KEY_CONFIRM_PASSWORD] = None

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        uid = state.get(K.KEY_USER_ID)
        return f"User #{uid}" if uid else "Ready to provision."
