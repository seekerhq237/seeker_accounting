from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPushButton, QVBoxLayout, QWidget


class BaseDialog(QDialog):
    def __init__(self, title: str, parent: QWidget | None = None, help_key: str | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(520, 320)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        self.body_layout = QVBoxLayout()
        self.body_layout.setSpacing(12)
        layout.addLayout(self.body_layout, 1)

        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        # ── Floating help button ──────────────────────────────────────────
        self._help_key = help_key
        self._help_btn: QPushButton | None = None
        if help_key:
            btn = QPushButton("?", self)
            btn.setObjectName("HelpButton")
            btn.setFixedSize(32, 32)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setToolTip("Help")
            btn.clicked.connect(self._show_help)
            self._help_btn = btn

    def _show_help(self) -> None:
        if self._help_key:
            from seeker_accounting.shared.ui.help_overlay import show_help_in_dialog
            show_help_in_dialog(self._help_key, self)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if self._help_btn is not None:
            self._help_btn.move(16, self.height() - 48)

    # ── License write guard ───────────────────────────────────────────────

    def _apply_license_guard(self, license_service: object) -> None:
        """
        Visually disable all accept-type buttons (Save / OK / Submit) when the
        installation is in read-only mode, and add a small notice label.

        Pass a ``LicenseService`` instance.  Uses duck-typing so this module
        stays import-free of platform.licensing at class-definition time.
        """
        try:
            is_permitted: bool = license_service.is_write_permitted()  # type: ignore[attr-defined]
        except Exception:
            return

        if is_permitted:
            return

        # Disable accept-type buttons in the button_box
        for btn in self.button_box.buttons():
            role = self.button_box.buttonRole(btn)
            if role in {
                QDialogButtonBox.ButtonRole.AcceptRole,
                QDialogButtonBox.ButtonRole.YesRole,
                QDialogButtonBox.ButtonRole.ApplyRole,
            }:
                btn.setEnabled(False)
                btn.setToolTip("Read-only mode — activate a license to enable this action.")

        # Add a notice label below the button box
        notice = QLabel("Read-only mode — activate a license to make changes.", self)
        notice.setObjectName("ReadOnlyNoticeLabel")
        notice.setWordWrap(True)
        layout = self.layout()
        if layout is not None:
            layout.addWidget(notice)


def check_write_or_raise(license_service: object) -> None:
    """
    Raise ``LicenseLimitedError`` if the installation is in read-only mode.

    Call this at the start of any dialog save handler before invoking services.

    Example::

        def _on_save(self) -> None:
            check_write_or_raise(self._license_service)
            self._my_service.create(...)
    """
    try:
        license_service.ensure_write_permitted()  # type: ignore[attr-defined]
    except AttributeError:
        # Graceful degradation if an unexpected object is passed
        pass

