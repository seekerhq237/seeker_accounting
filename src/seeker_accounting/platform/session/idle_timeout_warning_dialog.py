"""Idle timeout warning dialog — 30-second countdown before auto-logout."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class IdleTimeoutWarningDialog(QDialog):
    """Non-modal countdown dialog shown before automatic session logout."""

    stay_logged_in_requested = Signal()

    def __init__(
        self,
        seconds_remaining: int = 30,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Session Timeout")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
        )
        self.setModal(False)
        self.setFixedSize(380, 180)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title = QLabel("Are you still there?", self)
        title.setObjectName("DialogSectionTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self._countdown_label = QLabel(self)
        self._countdown_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._countdown_label.setWordWrap(True)
        self._update_text(seconds_remaining)
        layout.addWidget(self._countdown_label)

        layout.addStretch(1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.addStretch(1)

        stay_btn = QPushButton("Stay Logged In", self)
        stay_btn.setProperty("variant", "primary")
        stay_btn.setDefault(True)
        stay_btn.clicked.connect(self._on_stay)
        btn_row.addWidget(stay_btn)

        btn_row.addStretch(1)
        layout.addLayout(btn_row)

    def update_countdown(self, seconds_remaining: int) -> None:
        self._update_text(seconds_remaining)

    def _update_text(self, seconds: int) -> None:
        self._countdown_label.setText(
            f"You will be logged out due to inactivity in <b>{seconds}</b> second{'s' if seconds != 1 else ''}."
        )

    def _on_stay(self) -> None:
        self.stay_logged_in_requested.emit()
