"""Step 2 — Roles & company access."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
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


class RolesAccessStep(WizardStep):
    key = "roles_access"
    title = "Roles & access"
    subtitle = "Assign roles and grant access to the current company."

    def __init__(self) -> None:
        super().__init__()
        self._roles_list: QListWidget | None = None
        self._grant_current: QCheckBox | None = None
        self._is_default: QCheckBox | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        outer.addWidget(QLabel("Roles (multi-select):", root))
        self._roles_list = QListWidget(root)
        self._roles_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        outer.addWidget(self._roles_list, 1)

        self._grant_current = QCheckBox("Grant access to the current company", root)
        self._grant_current.setChecked(True)
        outer.addWidget(self._grant_current)

        self._is_default = QCheckBox("Set the current company as this user's default", root)
        self._is_default.setChecked(True)
        outer.addWidget(self._is_default)

        self._grant_current.toggled.connect(self._on_grant_toggled)
        return root

    def _on_grant_toggled(self, checked: bool) -> None:
        if self._is_default is not None:
            self._is_default.setEnabled(checked)
            if not checked:
                self._is_default.setChecked(False)

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._roles_list is not None and self._roles_list.count() == 0:
            try:
                roles = context.service_registry.user_auth_service.list_roles()
            except Exception:
                roles = []
            for role in roles:
                label = f"{role.code} \u2014 {role.name}"
                if getattr(role, "is_system", False):
                    label += "  (system)"
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, (int(role.id), str(role.code)))
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
                self._roles_list.addItem(item)

        prior = state.get(K.KEY_ROLE_IDS) or []
        prior_set = {int(r) for r in prior if isinstance(r, int)}
        if self._roles_list is not None and prior_set:
            for i in range(self._roles_list.count()):
                it = self._roles_list.item(i)
                payload = it.data(Qt.ItemDataRole.UserRole)
                if isinstance(payload, tuple) and int(payload[0]) in prior_set:
                    it.setCheckState(Qt.CheckState.Checked)

        if self._grant_current is not None:
            v = state.get(K.KEY_GRANT_CURRENT_COMPANY)
            self._grant_current.setChecked(True if v is None else bool(v))
        if self._is_default is not None:
            v = state.get(K.KEY_IS_DEFAULT_COMPANY)
            self._is_default.setChecked(True if v is None else bool(v))
            self._is_default.setEnabled(self._grant_current.isChecked() if self._grant_current else True)

    def write_back(self, state: WizardState) -> None:
        ids: list[int] = []
        codes: list[str] = []
        if self._roles_list is not None:
            for i in range(self._roles_list.count()):
                it = self._roles_list.item(i)
                if it.checkState() == Qt.CheckState.Checked:
                    payload = it.data(Qt.ItemDataRole.UserRole)
                    if isinstance(payload, tuple):
                        ids.append(int(payload[0]))
                        codes.append(str(payload[1]))
        state[K.KEY_ROLE_IDS] = ids
        state[K.KEY_ROLE_CODES] = codes
        if self._grant_current is not None:
            state[K.KEY_GRANT_CURRENT_COMPANY] = bool(self._grant_current.isChecked())
        if self._is_default is not None:
            state[K.KEY_IS_DEFAULT_COMPANY] = bool(self._is_default.isChecked())

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        # Roles and company access are optional; warn through the advisor instead.
        return StepValidationResult.ok()

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        codes = state.get(K.KEY_ROLE_CODES) or []
        if codes:
            return f"{len(codes)} role(s): {', '.join(codes)}"
        return "No roles assigned."
