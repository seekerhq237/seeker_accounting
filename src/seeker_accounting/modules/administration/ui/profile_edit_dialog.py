"""ProfileEditDialog - lightweight self-service profile editor."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.administration.dto.user_commands import UpdateUserCommand
from seeker_accounting.platform.exceptions import ValidationError
from seeker_accounting.shared.ui.avatar import apply_avatar_to_label
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.forms import create_field_block

_AVATAR_PREVIEW_SIZE = 72
_AVATAR_FILE_FILTER = "Images (*.png *.jpg *.jpeg *.webp)"


class ProfileEditDialog(BaseDialog):
    """Edit own display name, email address, and profile photo."""

    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__("Edit Profile", parent, help_key="dialog.profile_edit")
        self.resize(440, 420)
        self._service_registry = service_registry
        self._saved = False
        self._pending_avatar_path: str | None = None
        self._clear_avatar = False

        ctx = service_registry.app_context
        user_id = ctx.current_user_id
        if not isinstance(user_id, int) or user_id <= 0:
            raise RuntimeError("No authenticated user to edit.")

        user_dto = service_registry.user_auth_service.get_user(user_id)

        self._user_id = user_id
        self._original_must_change = user_dto.must_change_password
        self._stored_avatar_path = user_dto.avatar_storage_path

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

        username_display = QLineEdit(self)
        username_display.setText(user_dto.username)
        username_display.setReadOnly(True)
        self.body_layout.addWidget(create_field_block("Username", username_display))

        self._name_edit = QLineEdit(self)
        self._name_edit.setPlaceholderText("Full name or display name")
        self._name_edit.setText(user_dto.display_name)
        self._name_edit.textChanged.connect(self._refresh_avatar_preview_state)
        self.body_layout.addWidget(create_field_block("Display Name *", self._name_edit))

        self._email_edit = QLineEdit(self)
        self._email_edit.setPlaceholderText("Optional email address")
        if user_dto.email:
            self._email_edit.setText(user_dto.email)
        self.body_layout.addWidget(create_field_block("Email", self._email_edit))

        self.body_layout.addStretch(1)

        self.button_box.setStandardButtons(QDialogButtonBox.StandardButton.NoButton)

        save_btn = QPushButton("Save Changes", self)
        save_btn.setProperty("variant", "primary")
        save_btn.clicked.connect(self._handle_save)
        self.button_box.addButton(save_btn, QDialogButtonBox.ButtonRole.AcceptRole)

        cancel_btn = QPushButton("Cancel", self)
        cancel_btn.setProperty("variant", "secondary")
        cancel_btn.clicked.connect(self.reject)
        self.button_box.addButton(cancel_btn, QDialogButtonBox.ButtonRole.RejectRole)

        self._refresh_avatar_preview_state()

    @property
    def saved(self) -> bool:
        return self._saved

    @classmethod
    def prompt(cls, service_registry: ServiceRegistry, parent: QWidget | None = None) -> bool:
        """Show the dialog and return True if the profile was saved."""
        dialog = cls(service_registry, parent)
        dialog.exec()
        return dialog.saved

    def _handle_save(self) -> None:
        self._error_label.hide()
        display_name = self._name_edit.text().strip()
        email = self._email_edit.text().strip() or None

        if not display_name:
            self._show_error("Display name is required.")
            self._name_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return

        try:
            command = UpdateUserCommand(
                user_id=self._user_id,
                display_name=display_name,
                email=email,
                must_change_password=self._original_must_change,
            )
            self._service_registry.user_auth_service.update_user(command)
        except ValidationError as exc:
            self._show_error(str(exc))
            return
        except Exception as exc:
            self._show_error(str(exc))
            return

        self._apply_avatar_after_save()
        self._service_registry.app_context.current_user_display_name = display_name
        self._saved = True
        self.accept()

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

    def _apply_avatar_after_save(self) -> None:
        avatar_service = self._service_registry.user_avatar_service
        try:
            if self._clear_avatar:
                avatar_service.clear_avatar(self._user_id)
            elif self._pending_avatar_path:
                avatar_service.set_avatar(self._user_id, self._pending_avatar_path)
        except Exception:
            pass

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()
