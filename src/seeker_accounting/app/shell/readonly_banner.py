from __future__ import annotations

"""
ReadOnlyBanner — a fixed horizontal bar displayed below the topbar when the
installation is in read-only mode (trial or license expired).

The banner shows the expiry reason and an "Activate Now" button.
It is hidden when write operations are permitted.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

from seeker_accounting.platform.licensing.dto import LicenseInfo


class ReadOnlyBanner(QFrame):
    """
    Persistent warning strip shown at the top of the main content area.

    Signals
    -------
    activate_requested
        Emitted when the user clicks "Activate Now".
    """

    activate_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ReadOnlyBanner")
        self.setFixedHeight(36)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(12)

        self._message = QLabel("Read-only mode — your license has expired.", self)
        self._message.setObjectName("ReadOnlyBannerMessage")
        layout.addWidget(self._message, 1)

        self._activate_btn = QPushButton("Activate Now", self)
        self._activate_btn.setObjectName("ReadOnlyBannerActivate")
        self._activate_btn.setFixedHeight(24)
        self._activate_btn.clicked.connect(self.activate_requested.emit)
        layout.addWidget(self._activate_btn, 0)

        self.hide()

    # ── Public ────────────────────────────────────────────────────────

    def refresh(self, info: LicenseInfo) -> None:
        """Show or hide the banner based on *info*."""
        if info.is_write_permitted:
            self.hide()
        else:
            self._message.setText(f"Read-only mode — {info.summary}")
            self.show()
