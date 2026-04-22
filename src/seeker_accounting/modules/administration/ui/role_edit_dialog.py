"""Role create/edit dialog."""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QWidget,
)

from seeker_accounting.modules.administration.dto.role_commands import CreateRoleCommand, UpdateRoleCommand
from seeker_accounting.modules.administration.dto.user_dto import RoleDTO
from seeker_accounting.modules.administration.services.role_service import RoleService
from seeker_accounting.platform.exceptions import ConflictError, ValidationError
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.forms import create_field_block

logger = logging.getLogger(__name__)


class RoleEditDialog(BaseDialog):
    """Dialog for creating or editing a role."""

    def __init__(
        self,
        role_service: RoleService,
        role_dto: RoleDTO | None = None,
        parent: QWidget | None = None,
    ) -> None:
        title = "Edit Role" if role_dto else "New Role"
        super().__init__(title, parent, help_key="dialog.role_edit")
        self.setObjectName("RoleEditDialog")
        self.resize(460, 340)

        self._role_service = role_service
        self._role_dto = role_dto
        self._result: RoleDTO | None = None

        is_edit = role_dto is not None

        # --- Code ---
        self._code_edit = QLineEdit(self)
        self._code_edit.setPlaceholderText("e.g. warehouse_manager")
        if is_edit:
            self._code_edit.setText(role_dto.code)
            self._code_edit.setReadOnly(True)
            self._code_edit.setEnabled(False)
        self.body_layout.addWidget(create_field_block("Code", self._code_edit))

        # --- Name ---
        self._name_edit = QLineEdit(self)
        self._name_edit.setPlaceholderText("Role display name")
        if is_edit:
            self._name_edit.setText(role_dto.name)
        self.body_layout.addWidget(create_field_block("Name", self._name_edit))

        # --- Description ---
        self._description_edit = QTextEdit(self)
        self._description_edit.setPlaceholderText("Optional description…")
        self._description_edit.setMaximumHeight(80)
        if is_edit and role_dto.description:
            self._description_edit.setPlainText(role_dto.description)
        self.body_layout.addWidget(create_field_block("Description", self._description_edit))

        # --- System role warning ---
        if is_edit and role_dto.is_system:
            warning = QLabel("This is a system role. The code cannot be changed.", self)
            warning.setWordWrap(True)
            warning.setProperty("role", "caption")
            self.body_layout.addWidget(warning)

        # --- Error label ---
        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        self.body_layout.addWidget(self._error_label)

        self.body_layout.addStretch(1)

        # --- Buttons ---
        self.button_box.setStandardButtons(QDialogButtonBox.StandardButton.NoButton)

        save_btn = QPushButton("Save" if is_edit else "Create", self)
        save_btn.setProperty("variant", "primary")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._handle_save)
        self.button_box.addButton(save_btn, QDialogButtonBox.ButtonRole.AcceptRole)

        cancel_btn = QPushButton("Cancel", self)
        cancel_btn.setProperty("variant", "secondary")
        cancel_btn.clicked.connect(self.reject)
        self.button_box.addButton(cancel_btn, QDialogButtonBox.ButtonRole.RejectRole)

        self._name_edit.returnPressed.connect(self._handle_save)

    @property
    def result_dto(self) -> RoleDTO | None:
        return self._result

    # ── Class-level convenience ──────────────────────────────────────

    @classmethod
    def create_role(
        cls,
        role_service: RoleService,
        parent: QWidget | None = None,
    ) -> RoleDTO | None:
        dlg = cls(role_service=role_service, parent=parent)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.result_dto
        return None

    @classmethod
    def edit_role(
        cls,
        role_service: RoleService,
        role_dto: RoleDTO,
        parent: QWidget | None = None,
    ) -> RoleDTO | None:
        dlg = cls(role_service=role_service, role_dto=role_dto, parent=parent)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.result_dto
        return None

    # ── Internal ─────────────────────────────────────────────────────

    def _handle_save(self) -> None:
        self._error_label.hide()

        name = self._name_edit.text().strip()
        if not name:
            self._show_error("Name is required.")
            self._name_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return

        description = self._description_edit.toPlainText().strip() or None

        try:
            if self._role_dto is not None:
                result = self._role_service.update_role(
                    UpdateRoleCommand(
                        role_id=self._role_dto.id,
                        name=name,
                        description=description,
                    )
                )
            else:
                code = self._code_edit.text().strip()
                if not code:
                    self._show_error("Code is required.")
                    self._code_edit.setFocus(Qt.FocusReason.OtherFocusReason)
                    return
                result = self._role_service.create_role(
                    CreateRoleCommand(code=code, name=name, description=description)
                )
        except (ValidationError, ConflictError) as exc:
            self._show_error(str(exc))
            return
        except Exception:
            logger.exception("Unexpected error saving role.")
            self._show_error("An unexpected error occurred. Please try again.")
            return

        self._result = result
        self.accept()

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()
