from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.companies.services.system_admin_service import SystemAdminService
from seeker_accounting.platform.exceptions.app_exceptions import ValidationError


class SystemAdminPasswordChangeDialog(QDialog):
    """Forced first-use password change dialog for the system administrator.

    This dialog cannot be dismissed without successfully changing the password.
    It calls SystemAdminService.set_password_direct() which handles business rules:
    - minimum 8 characters
    - cannot remain "admin"
    - cannot be the same as the current password
    """

    def __init__(
        self,
        system_admin_service: SystemAdminService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = system_admin_service
        self._is_initial_setup = not system_admin_service.is_configured()

        self.setWindowTitle("Change System Administrator Password")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            # No close button — this dialog is mandatory
        )
        self.setFixedSize(440, 360)
        self.setModal(True)
        self._build_ui()

    # ── Public factory ────────────────────────────────────────────────────────

    @classmethod
    def prompt(
        cls,
        system_admin_service: SystemAdminService,
        parent: QWidget | None = None,
    ) -> None:
        """Show the forced change dialog and block until password is successfully changed."""
        dlg = cls(system_admin_service, parent)
        dlg.exec()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(12)

        warn_icon = QLabel("🔐")
        warn_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        warn_icon.setStyleSheet("font-size: 28px;")
        root.addWidget(warn_icon)

        heading = QLabel("Security Setup Required" if self._is_initial_setup else "Password Change Required")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setStyleSheet("font-size: 15px; font-weight: 700; color: #111827;")
        root.addWidget(heading)

        notice = QLabel(
            "Set the system administrator password before using this workflow.\n"
            "This password is used only for the system administration area."
            if self._is_initial_setup
            else "Please rotate the system administrator password before continuing."
        )
        notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
        notice.setWordWrap(True)
        notice.setStyleSheet(
            "font-size: 11px; color: #B45309; background: #FFFBEB; "
            "border: 1px solid #FDE68A; border-radius: 4px; padding: 8px;"
        )
        root.addWidget(notice)

        root.addSpacing(4)

        new_lbl = QLabel("New Password")
        new_lbl.setStyleSheet("font-size: 12px; color: #374151; font-weight: 600;")
        root.addWidget(new_lbl)

        self._new_password_field = QLineEdit()
        self._new_password_field.setEchoMode(QLineEdit.EchoMode.Password)
        self._new_password_field.setPlaceholderText("Minimum 8 characters")
        self._new_password_field.setFixedHeight(36)
        self._new_password_field.setStyleSheet(self._field_style())
        root.addWidget(self._new_password_field)

        confirm_lbl = QLabel("Confirm New Password")
        confirm_lbl.setStyleSheet("font-size: 12px; color: #374151; font-weight: 600;")
        root.addWidget(confirm_lbl)

        self._confirm_field = QLineEdit()
        self._confirm_field.setEchoMode(QLineEdit.EchoMode.Password)
        self._confirm_field.setPlaceholderText("Re-enter new password")
        self._confirm_field.setFixedHeight(36)
        self._confirm_field.setStyleSheet(self._field_style())
        self._confirm_field.returnPressed.connect(self._on_save)
        root.addWidget(self._confirm_field)

        save_btn = QPushButton("Set Password")
        save_btn.setFixedHeight(38)
        save_btn.setStyleSheet(
            "QPushButton { background: #059669; color: #fff; border: none; "
            "border-radius: 4px; font-size: 13px; font-weight: 600; }"
            "QPushButton:hover { background: #047857; }"
        )
        save_btn.clicked.connect(self._on_save)
        root.addWidget(save_btn)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _field_style() -> str:
        return (
            "QLineEdit { border: 1px solid #D1D5DB; border-radius: 4px; "
            "padding: 0 10px; font-size: 13px; color: #111827; background: #F9FAFB; }"
            "QLineEdit:focus { border-color: #3B82F6; background: #fff; }"
        )

    # ── Slot ──────────────────────────────────────────────────────────────────

    def _on_save(self) -> None:
        new_password = self._new_password_field.text()
        confirm = self._confirm_field.text()

        if not new_password:
            QMessageBox.warning(self, "Validation", "Please enter a new password.")
            return

        if new_password != confirm:
            QMessageBox.warning(self, "Validation", "Passwords do not match.")
            self._confirm_field.clear()
            return

        try:
            self._service.set_password_direct(new_password)
            QMessageBox.information(
                self,
                "Password Changed",
                "System administrator password has been updated successfully.",
            )
            self.accept()
        except ValidationError as exc:
            QMessageBox.warning(self, "Validation", str(exc))
            self._new_password_field.clear()
            self._confirm_field.clear()
            self._new_password_field.setFocus()

    # ── Prevent dismissal ─────────────────────────────────────────────────────

    def closeEvent(self, event):  # noqa: N802
        event.ignore()  # No close until password is changed

    def reject(self) -> None:
        pass  # Escape key does nothing
