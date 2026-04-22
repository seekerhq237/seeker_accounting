"""RoleAssignmentDialog — manage role assignments for a user."""
from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.administration.dto.user_dto import RoleDTO, UserDTO
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.message_boxes import show_error

logger = logging.getLogger(__name__)


class RoleAssignmentDialog(BaseDialog):
    """Add or remove roles assigned to a user.

    Use: ``RoleAssignmentDialog.manage(service_registry, user_dto, parent)``
    """

    def __init__(
        self,
        service_registry: ServiceRegistry,
        user_dto: UserDTO,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(f"Manage Roles — {user_dto.display_name}", parent, help_key="dialog.role_assignment")
        self.resize(500, 420)
        self._service_registry = service_registry
        self._user_dto = user_dto
        self._all_roles: list[RoleDTO] = []

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        self.body_layout.addWidget(self._error_label)

        current_lbl = QLabel("Current Roles", self)
        current_lbl.setObjectName("InfoCardTitle")
        self.body_layout.addWidget(current_lbl)

        self._roles_container = QWidget(self)
        self._roles_layout = QVBoxLayout(self._roles_container)
        self._roles_layout.setContentsMargins(0, 0, 0, 0)
        self._roles_layout.setSpacing(4)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setMaximumHeight(150)
        scroll.setWidget(self._roles_container)
        self.body_layout.addWidget(scroll)

        assign_lbl = QLabel("Assign New Role", self)
        assign_lbl.setObjectName("InfoCardTitle")
        self.body_layout.addWidget(assign_lbl)

        assign_row = QWidget(self)
        assign_layout = QHBoxLayout(assign_row)
        assign_layout.setContentsMargins(0, 0, 0, 0)
        assign_layout.setSpacing(8)

        self._role_combo = QComboBox(self)
        assign_layout.addWidget(self._role_combo, 1)

        assign_btn = QPushButton("Assign", self)
        assign_btn.setProperty("variant", "primary")
        assign_btn.clicked.connect(self._handle_assign)
        assign_layout.addWidget(assign_btn)

        self.body_layout.addWidget(assign_row)
        self.body_layout.addStretch(1)

        self.button_box.setStandardButtons(QDialogButtonBox.StandardButton.Close)

        self._load_all_roles()
        self._refresh_current_roles()

    @classmethod
    def manage(
        cls,
        service_registry: ServiceRegistry,
        user_dto: UserDTO,
        parent: QWidget | None = None,
    ) -> None:
        dialog = cls(service_registry=service_registry, user_dto=user_dto, parent=parent)
        dialog.exec()

    def _load_all_roles(self) -> None:
        try:
            self._all_roles = self._service_registry.user_auth_service.list_roles()
        except Exception:
            logger.exception("Failed to load available roles.")
            self._all_roles = []
            self._error_label.setText("Could not load roles. Please close and retry.")
            self._error_label.show()

    def _refresh_current_roles(self) -> None:
        self._error_label.hide()
        while self._roles_layout.count():
            item = self._roles_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        try:
            current_roles = self._service_registry.user_auth_service.get_user_roles(self._user_dto.id)
        except Exception:
            logger.exception("Failed to load current roles for user %s.", self._user_dto.id)
            current_roles = []
            self._error_label.setText("Could not load current roles. Please close and retry.")
            self._error_label.show()

        if not current_roles:
            empty = QLabel("No roles assigned.", self._roles_container)
            empty.setObjectName("PageSummary")
            self._roles_layout.addWidget(empty)
        else:
            for role in current_roles:
                self._roles_layout.addWidget(self._build_role_row(role))

        self._roles_layout.addStretch(1)

        assigned_ids = {r.id for r in current_roles}
        self._role_combo.clear()
        for role in self._all_roles:
            if role.id not in assigned_ids:
                self._role_combo.addItem(role.name, role.id)

    def _build_role_row(self, role: RoleDTO) -> QWidget:
        row = QWidget(self._roles_container)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(8)

        label = QLabel(role.name, row)
        layout.addWidget(label, 1)

        remove_btn = QPushButton("Remove", row)
        remove_btn.setProperty("variant", "secondary")
        remove_btn.setFixedWidth(80)
        remove_btn.clicked.connect(lambda checked=False, rid=role.id: self._handle_revoke(rid))
        layout.addWidget(remove_btn)
        return row

    def _handle_assign(self) -> None:
        self._error_label.hide()
        if self._role_combo.count() == 0:
            return
        role_id = self._role_combo.currentData()
        if role_id is None:
            return
        try:
            self._service_registry.user_auth_service.assign_role(
                user_id=self._user_dto.id,
                role_id=role_id,
            )
            self._refresh_current_roles()
        except Exception as exc:
            self._error_label.setText(str(exc))
            self._error_label.show()

    def _handle_revoke(self, role_id: int) -> None:
        self._error_label.hide()
        try:
            self._service_registry.user_auth_service.revoke_role(
                user_id=self._user_dto.id,
                role_id=role_id,
            )
            self._refresh_current_roles()
        except Exception as exc:
            self._error_label.setText(str(exc))
            self._error_label.show()
