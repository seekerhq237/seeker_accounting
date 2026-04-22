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


class SystemAdminAuthDialog(QDialog):
    """Authentication gate for the system administration area.

    Completely isolated from the application's normal login flow.
    Does NOT inherit BaseDialog.
    """

    def __init__(
        self,
        system_admin_service: SystemAdminService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = system_admin_service
        self._authenticated = False

        self.setWindowTitle("System Administration")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setFixedSize(400, 300)
        self.setModal(True)
        self._build_ui()

    # ── Public factory ────────────────────────────────────────────────────────

    @classmethod
    def authenticate(
        cls,
        system_admin_service: SystemAdminService,
        parent: QWidget | None = None,
    ) -> bool:
        """Show the dialog and return True only if credentials were accepted."""
        dlg = cls(system_admin_service, parent)
        dlg.exec()
        return dlg._authenticated

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 24)
        root.setSpacing(14)

        icon = QLabel("⚙")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 30px; color: #374151;")
        root.addWidget(icon)

        heading = QLabel("System Administration")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setStyleSheet("font-size: 16px; font-weight: 600; color: #111827;")
        root.addWidget(heading)

        sub = QLabel("Enter system administrator credentials to continue.")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setWordWrap(True)
        sub.setStyleSheet("font-size: 11px; color: #6B7280;")
        root.addWidget(sub)

        root.addSpacing(4)

        self._username_field = QLineEdit()
        self._username_field.setPlaceholderText("Username")
        self._username_field.setText("sysadmin")
        self._username_field.setFixedHeight(36)
        self._username_field.setStyleSheet(self._field_style())
        root.addWidget(self._username_field)

        self._password_field = QLineEdit()
        self._password_field.setPlaceholderText("Password")
        self._password_field.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_field.setFixedHeight(36)
        self._password_field.setStyleSheet(self._field_style())
        self._password_field.returnPressed.connect(self._on_unlock)
        root.addWidget(self._password_field)

        unlock_btn = QPushButton("Unlock")
        unlock_btn.setFixedHeight(38)
        unlock_btn.setStyleSheet(
            "QPushButton { background: #1D4ED8; color: #fff; border: none; "
            "border-radius: 4px; font-size: 13px; font-weight: 600; }"
            "QPushButton:hover { background: #1E40AF; }"
        )
        unlock_btn.clicked.connect(self._on_unlock)
        root.addWidget(unlock_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFlat(True)
        cancel_btn.setFixedHeight(32)
        cancel_btn.setStyleSheet(
            "QPushButton { color: #6B7280; border: none; font-size: 12px; }"
            "QPushButton:hover { color: #374151; }"
        )
        cancel_btn.clicked.connect(self.reject)
        root.addWidget(cancel_btn)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_unlock(self) -> None:
        username = self._username_field.text().strip()
        password = self._password_field.text()

        if not username or not password:
            self._show_error("Please enter both username and password.")
            return

        if self._service.verify_credentials(username, password):
            self._authenticated = True
            self.accept()
        else:
            self._password_field.clear()
            self._show_error("Invalid credentials. Please try again.")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, "Authentication Failed", message)

    @staticmethod
    def _field_style() -> str:
        return (
            "QLineEdit { border: 1px solid #D1D5DB; border-radius: 4px; "
            "padding: 0 10px; font-size: 13px; color: #111827; background: #F9FAFB; }"
            "QLineEdit:focus { border-color: #3B82F6; background: #fff; }"
        )
