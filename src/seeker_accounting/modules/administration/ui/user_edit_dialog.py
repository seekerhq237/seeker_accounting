"""UserEditDialog - create or edit a user account."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.administration.dto.user_commands import (
    CreateUserCommand,
    UpdateUserCommand,
)
from seeker_accounting.modules.administration.dto.user_dto import UserDTO
from seeker_accounting.platform.exceptions import ConflictError, ValidationError
from seeker_accounting.shared.ui.avatar import apply_avatar_to_label
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.forms import create_field_block

_AVATAR_PREVIEW_SIZE = 72
_AVATAR_FILE_FILTER = "Images (*.png *.jpg *.jpeg *.webp)"


class UserEditDialog(BaseDialog):
    """Create or edit a user account.

    Use static factory methods:
    - ``UserEditDialog.create_user(service_registry, company_id, parent)``
    - ``UserEditDialog.edit_user(service_registry, user_dto, parent)``
    """

    def __init__(
        self,
        service_registry: ServiceRegistry,
        mode: str,
        company_id: int | None = None,
        user_dto: UserDTO | None = None,
        parent: QWidget | None = None,
    ) -> None:
        title = "New User" if mode == "create" else "Edit User"
        super().__init__(title, parent, help_key="dialog.user_edit")
        self.resize(460, 520 if mode == "create" else 430)
        self._service_registry = service_registry
        self._mode = mode
        self._company_id = company_id
        self._user_dto = user_dto
        self._result_dto: UserDTO | None = None
        self._pending_avatar_path: str | None = None
        self._clear_avatar = False
        self._stored_avatar_path = user_dto.avatar_storage_path if user_dto else None

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        self.body_layout.addWidget(self._error_label)

        photo_label = QLabel("Profile Photo", self)
        photo_label.setObjectName("FieldLabel")
        self.body_layout.addWidget(photo_label)

        self._avatar_preview = QLabel(self)
        self._avatar_preview.setObjectName("UserAvatarPreview")
        self._avatar_preview.setFixedSize(_AVATAR_PREVIEW_SIZE, _AVATAR_PREVIEW_SIZE)
        self._avatar_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.body_layout.addWidget(self._avatar_preview)

        self._choose_avatar_btn = QPushButton("Choose Photo...", self)
        self._choose_avatar_btn.setProperty("variant", "secondary")
        self._choose_avatar_btn.setFixedHeight(28)
        self._choose_avatar_btn.clicked.connect(self._handle_choose_avatar)

        self._remove_avatar_btn = QPushButton("Remove", self)
        self._remove_avatar_btn.setProperty("variant", "secondary")
        self._remove_avatar_btn.setFixedHeight(28)
        self._remove_avatar_btn.clicked.connect(self._handle_remove_avatar)

        avatar_button_row = QWidget(self)
        avatar_button_layout = QHBoxLayout(avatar_button_row)
        avatar_button_layout.setContentsMargins(0, 4, 0, 8)
        avatar_button_layout.setSpacing(8)
        avatar_button_layout.addWidget(self._choose_avatar_btn)
        avatar_button_layout.addWidget(self._remove_avatar_btn)
        avatar_button_layout.addStretch(1)
        self.body_layout.addWidget(avatar_button_row)

        photo_hint = QLabel("PNG, JPG, or WEBP up to 2 MB.", self)
        photo_hint.setProperty("role", "caption")
        self.body_layout.addWidget(photo_hint)

        self._name_edit = QLineEdit(self)
        self._name_edit.setPlaceholderText("Full name or display name")
        if user_dto:
            self._name_edit.setText(user_dto.display_name)
        self._name_edit.textChanged.connect(self._refresh_avatar_preview_state)
        self.body_layout.addWidget(create_field_block("Display Name *", self._name_edit))

        self._username_edit = QLineEdit(self)
        if mode == "create":
            self._username_edit.setPlaceholderText("Unique login identifier")
        else:
            self._username_edit.setText(user_dto.username if user_dto else "")
            self._username_edit.setReadOnly(True)
        self.body_layout.addWidget(create_field_block("Username *", self._username_edit))

        self._email_edit = QLineEdit(self)
        self._email_edit.setPlaceholderText("Optional email address")
        if user_dto and user_dto.email:
            self._email_edit.setText(user_dto.email)
        self.body_layout.addWidget(create_field_block("Email", self._email_edit))

        if mode == "create":
            self._password_edit = QLineEdit(self)
            self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self._password_edit.setPlaceholderText("Set initial password")
            self.body_layout.addWidget(create_field_block("Password *", self._password_edit))

            self._confirm_edit = QLineEdit(self)
            self._confirm_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self._confirm_edit.setPlaceholderText("Confirm password")
            self.body_layout.addWidget(create_field_block("Confirm Password *", self._confirm_edit))

        self._must_change_cb = QCheckBox("User must change password on next login", self)
        if user_dto:
            self._must_change_cb.setChecked(user_dto.must_change_password)
        self.body_layout.addWidget(self._must_change_cb)
        self.body_layout.addStretch(1)

        self.button_box.setStandardButtons(QDialogButtonBox.StandardButton.NoButton)
        save_btn = QPushButton("Create User" if mode == "create" else "Save Changes", self)
        save_btn.setProperty("variant", "primary")
        save_btn.clicked.connect(self._handle_save)
        self.button_box.addButton(save_btn, QDialogButtonBox.ButtonRole.AcceptRole)

        cancel_btn = QPushButton("Cancel", self)
        cancel_btn.setProperty("variant", "secondary")
        cancel_btn.clicked.connect(self.reject)
        self.button_box.addButton(cancel_btn, QDialogButtonBox.ButtonRole.RejectRole)

        self._refresh_avatar_preview_state()

    @property
    def result_dto(self) -> UserDTO | None:
        return self._result_dto

    @classmethod
    def create_user(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        parent: QWidget | None = None,
    ) -> UserDTO | None:
        dialog = cls(
            service_registry=service_registry,
            mode="create",
            company_id=company_id,
            parent=parent,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.result_dto
        return None

    @classmethod
    def edit_user(
        cls,
        service_registry: ServiceRegistry,
        user_dto: UserDTO,
        parent: QWidget | None = None,
    ) -> UserDTO | None:
        dialog = cls(
            service_registry=service_registry,
            mode="edit",
            user_dto=user_dto,
            parent=parent,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.result_dto
        return None

    def _handle_save(self) -> None:
        self._error_label.hide()
        auth_service = self._service_registry.user_auth_service
        if self._mode == "create":
            self._handle_create(auth_service)
        else:
            self._handle_edit(auth_service)

    def _handle_create(self, auth_service) -> None:
        display_name = self._name_edit.text().strip()
        username = self._username_edit.text().strip()
        password = self._password_edit.text()
        confirm = self._confirm_edit.text()
        email = self._email_edit.text().strip() or None

        if not display_name:
            self._show_error("Display name is required.")
            self._name_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        if not username:
            self._show_error("Username is required.")
            self._username_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        if not password:
            self._show_error("Password is required.")
            self._password_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        if password != confirm:
            self._show_error("Passwords do not match.")
            self._confirm_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return

        try:
            command = CreateUserCommand(
                username=username,
                display_name=display_name,
                password=password,
                email=email,
                must_change_password=self._must_change_cb.isChecked(),
            )
            new_user = auth_service.create_user(command)
            if self._company_id is not None:
                current_user_id = self._service_registry.app_context.current_user_id
                auth_service.grant_company_access(
                    user_id=new_user.id,
                    company_id=self._company_id,
                    granted_by_user_id=current_user_id,
                )
            self._apply_avatar_after_save(new_user.id)
            self._result_dto = new_user
            self.accept()
        except (ValidationError, ConflictError) as exc:
            self._show_error(str(exc))
        except Exception as exc:
            self._show_error(str(exc))

    def _handle_edit(self, auth_service) -> None:
        display_name = self._name_edit.text().strip()
        email = self._email_edit.text().strip() or None

        if not display_name:
            self._show_error("Display name is required.")
            self._name_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return

        try:
            command = UpdateUserCommand(
                user_id=self._user_dto.id,
                display_name=display_name,
                email=email,
                must_change_password=self._must_change_cb.isChecked(),
            )
            updated = auth_service.update_user(command)
            self._apply_avatar_after_save(self._user_dto.id)
            self._result_dto = updated
            self.accept()
        except ValidationError as exc:
            self._show_error(str(exc))
        except Exception as exc:
            self._show_error(str(exc))

    def _handle_choose_avatar(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose Profile Photo", "", _AVATAR_FILE_FILTER)
        if not path:
            return

        avatar_service = self._service_registry.user_avatar_service
        try:
            avatar_service.validate_avatar_file(path)
        except ValidationError as exc:
            self._show_error(str(exc))
            return

        self._error_label.hide()
        self._pending_avatar_path = path
        self._clear_avatar = False
        self._refresh_avatar_preview_state()

    def _handle_remove_avatar(self) -> None:
        self._pending_avatar_path = None
        self._clear_avatar = True
        self._refresh_avatar_preview_state()

    def _refresh_avatar_preview_state(self, _text: str | None = None) -> None:
        if self._pending_avatar_path:
            self._set_avatar_preview_image(self._pending_avatar_path)
            self._remove_avatar_btn.show()
            return

        if not self._clear_avatar and self._stored_avatar_path:
            resolved = self._service_registry.user_avatar_service.resolve_avatar_path(self._stored_avatar_path)
            if resolved is not None:
                self._set_avatar_preview_image(str(resolved))
                self._remove_avatar_btn.show()
                return
            self._set_avatar_preview_fallback(show_remove=True)
            return

        self._set_avatar_preview_fallback(show_remove=False)

    def _set_avatar_preview_image(self, image_path: str) -> None:
        if not apply_avatar_to_label(
            self._avatar_preview,
            display_name=self._current_avatar_name(),
            size=_AVATAR_PREVIEW_SIZE,
            image_path=image_path,
        ):
            self._set_avatar_preview_fallback(show_remove=bool(self._stored_avatar_path or self._pending_avatar_path))

    def _set_avatar_preview_fallback(self, *, show_remove: bool) -> None:
        apply_avatar_to_label(
            self._avatar_preview,
            display_name=self._current_avatar_name(),
            size=_AVATAR_PREVIEW_SIZE,
        )
        self._remove_avatar_btn.setVisible(show_remove)

    def _current_avatar_name(self) -> str:
        return self._name_edit.text().strip() or "User"

    def _apply_avatar_after_save(self, user_id: int) -> None:
        avatar_service = self._service_registry.user_avatar_service
        try:
            if self._clear_avatar:
                avatar_service.clear_avatar(user_id)
            elif self._pending_avatar_path:
                avatar_service.set_avatar(user_id, self._pending_avatar_path)
        except Exception:
            pass

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()
