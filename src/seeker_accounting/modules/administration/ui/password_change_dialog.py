"""Password change dialog for mandatory resets and self-service changes."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.forms import create_field_block


@dataclass(frozen=True, slots=True)
class PasswordChangeResult:
    new_password: str
    current_password: str | None = None


class PasswordChangeDialog(BaseDialog):
    """Prompt a user to choose a new password."""

    def __init__(
        self,
        username: str,
        allow_skip: bool = True,
        require_current_password: bool = False,
        title: str = "Change Password",
        submit_label: str = "Change Password",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(title, parent, help_key="dialog.password_change")
        self.setObjectName("PasswordChangeDialog")
        self.resize(400, 240 if require_current_password else 200)

        self._allow_skip = allow_skip
        self._result: PasswordChangeResult | None = None

        if not allow_skip:
            self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        self.body_layout.addWidget(self._error_label)

        self._summary_label = QLabel(f"Set a secure password for {username}.", self)
        self._summary_label.setWordWrap(True)
        self.body_layout.addWidget(self._summary_label)

        self._require_current_password = require_current_password
        self._current_password_edit: QLineEdit | None = None
        if require_current_password:
            self._current_password_edit = QLineEdit(self)
            self._current_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self._current_password_edit.setPlaceholderText("Current password")
            self.body_layout.addWidget(create_field_block("Current Password", self._current_password_edit))

        self._password_edit = QLineEdit(self)
        self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_edit.setPlaceholderText("New password")
        self._toggle_pw_action = QAction("Show", self._password_edit)
        self._toggle_pw_action.setToolTip("Show or hide password")
        self._toggle_pw_action.triggered.connect(self._toggle_password_visibility)
        self._password_edit.addAction(
            self._toggle_pw_action, QLineEdit.ActionPosition.TrailingPosition
        )
        self.body_layout.addWidget(create_field_block("New Password", self._password_edit))

        self._confirm_edit = QLineEdit(self)
        self._confirm_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._confirm_edit.setPlaceholderText("Confirm password")
        self._toggle_confirm_action = QAction("Show", self._confirm_edit)
        self._toggle_confirm_action.setToolTip("Show or hide password")
        self._toggle_confirm_action.triggered.connect(self._toggle_confirm_visibility)
        self._confirm_edit.addAction(
            self._toggle_confirm_action, QLineEdit.ActionPosition.TrailingPosition
        )
        self.body_layout.addWidget(create_field_block("Confirm Password", self._confirm_edit))

        self.body_layout.addStretch(1)

        self.button_box.setStandardButtons(QDialogButtonBox.StandardButton.NoButton)

        change_btn = QPushButton(submit_label, self)
        change_btn.setProperty("variant", "primary")
        change_btn.clicked.connect(self._handle_change)
        self.button_box.addButton(change_btn, QDialogButtonBox.ButtonRole.AcceptRole)

        if allow_skip:
            skip_btn = QPushButton("Skip for Now", self)
            skip_btn.setProperty("variant", "secondary")
            skip_btn.clicked.connect(self.reject)
            self.button_box.addButton(skip_btn, QDialogButtonBox.ButtonRole.RejectRole)

    @property
    def result(self) -> PasswordChangeResult | None:
        return self._result

    @classmethod
    def prompt(
        cls,
        username: str,
        allow_skip: bool = True,
        require_current_password: bool = False,
        title: str = "Change Password",
        submit_label: str = "Change Password",
        parent: QWidget | None = None,
    ) -> PasswordChangeResult | None:
        dialog = cls(
            username=username,
            allow_skip=allow_skip,
            require_current_password=require_current_password,
            title=title,
            submit_label=submit_label,
            parent=parent,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.result
        return None

    def _toggle_password_visibility(self) -> None:
        if self._password_edit.echoMode() == QLineEdit.EchoMode.Password:
            self._password_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self._toggle_pw_action.setText("Hide")
        else:
            self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self._toggle_pw_action.setText("Show")

    def _toggle_confirm_visibility(self) -> None:
        if self._confirm_edit.echoMode() == QLineEdit.EchoMode.Password:
            self._confirm_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self._toggle_confirm_action.setText("Hide")
        else:
            self._confirm_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self._toggle_confirm_action.setText("Show")

    def _handle_change(self) -> None:
        self._error_label.hide()
        current_password: str | None = None

        if self._require_current_password and self._current_password_edit is not None:
            current_password = self._current_password_edit.text()
            if not current_password:
                self._error_label.setText("Current password is required.")
                self._error_label.show()
                self._current_password_edit.setFocus(Qt.FocusReason.OtherFocusReason)
                return

        password = self._password_edit.text()
        confirm = self._confirm_edit.text()

        if not password:
            self._error_label.setText("Password is required.")
            self._error_label.show()
            self._password_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        if len(password) < 8:
            self._error_label.setText("Password must be at least 8 characters.")
            self._error_label.show()
            self._password_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        if password != confirm:
            self._error_label.setText("Passwords do not match.")
            self._error_label.show()
            self._confirm_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return

        self._result = PasswordChangeResult(
            new_password=password,
            current_password=current_password,
        )
        self.accept()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if not self._allow_skip:
            event.ignore()
            return
        super().closeEvent(event)

    def reject(self) -> None:
        if not self._allow_skip:
            return
        super().reject()
