from __future__ import annotations

"""
LicenseDialog — lets the user view their license state and activate / deactivate
a license key.

This dialog is opened from:
  - The topbar license chip
  - The read-only banner "Activate Now" button
  - The profile menu "License…" item
  - The pre-login landing window / splash screen
"""

import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.platform.licensing.dto import LicenseInfo, LicenseState
from seeker_accounting.platform.licensing.license_service import LicenseService
from seeker_accounting.shared.ui.message_boxes import show_error, show_info

logger = logging.getLogger(__name__)

_MAX_LICENSE_FILE_BYTES = 4096


class LicenseDialog(QDialog):
    """
    Modal dialog for managing the installation license.

    Use the class method ``show_modal(license_service, parent)`` to open it.
    """

    def __init__(self, license_service: LicenseService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._license_service = license_service

        self.setWindowTitle("License Management")
        self.setModal(True)
        self.setMinimumWidth(480)
        self.resize(520, 380)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 20)
        root.setSpacing(18)

        # ── Status card ───────────────────────────────────────────────
        self._status_card = self._build_status_card()
        root.addWidget(self._status_card)

        # ── Separator ─────────────────────────────────────────────────
        sep = QFrame(self)
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("DialogSeparator")
        root.addWidget(sep)

        # ── Activation area ───────────────────────────────────────────
        root.addWidget(QLabel("Enter a license key to activate:", self))

        key_row = QHBoxLayout()
        key_row.setSpacing(8)
        self._key_input = QLineEdit(self)
        self._key_input.setPlaceholderText("SEEKER-…")
        self._key_input.setObjectName("LicenseKeyInput")
        self._key_input.textChanged.connect(self._on_key_changed)
        key_row.addWidget(self._key_input, 1)

        self._import_btn = QPushButton("Import File…", self)
        self._import_btn.setToolTip("Load a license key from a .lic or .txt file.")
        self._import_btn.clicked.connect(self._on_import_file)
        key_row.addWidget(self._import_btn, 0)
        root.addLayout(key_row)

        self._feedback = QLabel("", self)
        self._feedback.setObjectName("LicenseFeedback")
        self._feedback.setWordWrap(True)
        self._feedback.setVisible(False)
        root.addWidget(self._feedback)

        root.addStretch(1)

        # ── Buttons ───────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._deactivate_btn = QPushButton("Deactivate", self)
        self._deactivate_btn.setObjectName("DeactivateButton")
        self._deactivate_btn.setToolTip("Remove the current license key and revert to trial mode.")
        self._deactivate_btn.clicked.connect(self._on_deactivate)
        btn_row.addWidget(self._deactivate_btn)

        btn_row.addStretch(1)

        self._activate_btn = QPushButton("Activate", self)
        self._activate_btn.setDefault(True)
        self._activate_btn.setEnabled(False)
        self._activate_btn.clicked.connect(self._on_activate)
        btn_row.addWidget(self._activate_btn)

        close_btn = QPushButton("Close", self)
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)

        root.addLayout(btn_row)

        self._refresh_display()

    # ── Class method entry point ──────────────────────────────────────

    @classmethod
    def show_modal(
        cls,
        license_service: LicenseService,
        parent: QWidget | None = None,
    ) -> None:
        """Instantiate and exec the dialog."""
        dialog = cls(license_service, parent)
        dialog.exec()

    # ── Build helpers ─────────────────────────────────────────────────

    def _build_status_card(self) -> QFrame:
        card = QFrame(self)
        card.setObjectName("LicenseStatusCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        header_row = QHBoxLayout()
        self._state_icon = QLabel("", card)
        self._state_icon.setObjectName("LicenseStateIcon")
        self._state_icon.setFixedWidth(18)
        header_row.addWidget(self._state_icon, 0, Qt.AlignmentFlag.AlignVCenter)

        self._state_label = QLabel("", card)
        self._state_label.setObjectName("LicenseStateTitle")
        header_row.addWidget(self._state_label, 1, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(header_row)

        self._detail_label = QLabel("", card)
        self._detail_label.setObjectName("LicenseDetail")
        self._detail_label.setWordWrap(True)
        layout.addWidget(self._detail_label)
        return card

    # ── Internal ──────────────────────────────────────────────────────

    def _refresh_display(self) -> None:
        info = self._license_service.get_license_info(bypass_cache=True)
        self._apply_status(info)
        has_license = info.state in {LicenseState.LICENSED_ACTIVE, LicenseState.LICENSED_EXPIRED}
        self._deactivate_btn.setVisible(has_license)

    def _apply_status(self, info: LicenseInfo) -> None:
        state = info.state
        icon_map = {
            LicenseState.LICENSED_ACTIVE: "●",
            LicenseState.LICENSED_EXPIRED: "●",
            LicenseState.TRIAL_ACTIVE: "◌",
            LicenseState.TRIAL_EXPIRED: "●",
        }
        title_map = {
            LicenseState.LICENSED_ACTIVE: "Licensed",
            LicenseState.LICENSED_EXPIRED: "License Expired",
            LicenseState.TRIAL_ACTIVE: f"Trial Mode — {info.trial_days_remaining} day(s) remaining",
            LicenseState.TRIAL_EXPIRED: "Trial Expired",
        }
        tone_map = {
            LicenseState.LICENSED_ACTIVE: "success",
            LicenseState.LICENSED_EXPIRED: "danger",
            LicenseState.TRIAL_ACTIVE: "neutral",
            LicenseState.TRIAL_EXPIRED: "danger",
        }

        self._state_icon.setText(icon_map.get(state, "●"))
        self._state_icon.setProperty("licenseStateTone", tone_map.get(state, "neutral"))
        self._state_icon.style().unpolish(self._state_icon)
        self._state_icon.style().polish(self._state_icon)

        self._state_label.setText(title_map.get(state, info.summary))

        if state == LicenseState.LICENSED_ACTIVE and info.license_expires_at:
            detail = f"Valid until {info.license_expires_at.isoformat()}."
        elif state == LicenseState.LICENSED_EXPIRED and info.license_expires_at:
            detail = f"Expired on {info.license_expires_at.isoformat()}. Please enter a new license key."
        elif state == LicenseState.TRIAL_ACTIVE:
            detail = "You are in trial mode. Enter a license key to unlock the full product."
        else:
            detail = "Your trial has ended. Enter a license key to continue using Seeker Accounting."

        self._detail_label.setText(detail)

    def _on_key_changed(self, text: str) -> None:
        stripped = text.strip()
        self._activate_btn.setEnabled(len(stripped) > 10)
        self._feedback.setVisible(False)

    def _on_activate(self) -> None:
        key = self._key_input.text().strip()
        if not key:
            return
        try:
            self._license_service.activate_license(key)
            show_info(self, "License Activated", "Your license key has been activated successfully.")
            self._key_input.clear()
            self._set_feedback("", success=True)
            self._refresh_display()
        except ValueError as exc:
            self._set_feedback(str(exc), success=False)
        except Exception as exc:
            show_error(self, "Activation Error", f"Unexpected error during activation:\n\n{exc}")

    def _on_deactivate(self) -> None:
        self._license_service.deactivate_license()
        show_info(
            self,
            "License Removed",
            "The license has been removed. The application will revert to trial or expired mode.",
        )
        self._refresh_display()

    def _on_import_file(self) -> None:
        """Open a file dialog and load the key from a .lic or .txt file."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import License Key",
            "",
            "License Files (*.lic *.txt);;All Files (*)",
        )
        if not path:
            return

        file_path = Path(path)
        try:
            size = file_path.stat().st_size
            if size > _MAX_LICENSE_FILE_BYTES:
                self._set_feedback(
                    f"File is too large ({size:,} bytes). License key files should be under {_MAX_LICENSE_FILE_BYTES:,} bytes.",
                    success=False,
                )
                return
            content = file_path.read_text(encoding="utf-8").strip()
        except Exception as exc:
            logger.warning("Failed to read license file %s: %s", file_path, exc)
            self._set_feedback("Could not read the selected file.", success=False)
            return

        if not content:
            self._set_feedback("The selected file is empty.", success=False)
            return

        # Take only the first non-empty line (the key itself).
        first_line = content.splitlines()[0].strip()
        if not first_line:
            self._set_feedback("No license key found in the file.", success=False)
            return

        self._key_input.setText(first_line)
        self._set_feedback("", success=True)

    def _set_feedback(self, message: str, *, success: bool) -> None:
        if not message:
            self._feedback.setVisible(False)
            return
        self._feedback.setText(message)
        self._feedback.setProperty("feedbackTone", "success" if success else "danger")
        self._feedback.style().unpolish(self._feedback)
        self._feedback.style().polish(self._feedback)
        self._feedback.setVisible(True)
