from __future__ import annotations

"""
LicenseStatusChip — compact topbar widget showing the current license state.

Clicking the chip opens the LicenseDialog.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

from seeker_accounting.platform.licensing.dto import LicenseInfo, LicenseState


class LicenseStatusChip(QFrame):
    """
    Small clickable chip displayed in the topbar.

    Emits ``activate_requested`` when the user clicks it so that the parent
    can show the LicenseDialog without this widget needing to own it.
    """

    activate_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("TopBarLicenseChip")
        self.setProperty("licenseState", "trial_active")
        self.setFixedHeight(20)
        self.setMinimumWidth(60)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("License status — click to manage")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        layout.setSpacing(4)

        self._dot = QLabel(self)
        self._dot.setObjectName("TopBarStatusDot")
        self._dot.setProperty("statusTone", "neutral")
        self._dot.setFixedSize(6, 6)
        layout.addWidget(self._dot, 0, Qt.AlignmentFlag.AlignVCenter)

        self._label = QLabel("Trial", self)
        self._label.setObjectName("TopBarChipValue")
        layout.addWidget(self._label, 0, Qt.AlignmentFlag.AlignVCenter)

    # ── Public ────────────────────────────────────────────────────────

    def refresh(self, info: LicenseInfo) -> None:
        """Update the chip to reflect *info*."""
        text, tone, state_str, tooltip = self._resolve_display(info)
        self._label.setText(text)
        self._set_tone(tone)
        self.setProperty("licenseState", state_str)
        self.style().unpolish(self)
        self.style().polish(self)
        self.setToolTip(tooltip)

    # ── Interaction ───────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.activate_requested.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    # ── Internal helpers ──────────────────────────────────────────────

    def _set_tone(self, tone: str) -> None:
        self._dot.setProperty("statusTone", tone)
        self._dot.style().unpolish(self._dot)
        self._dot.style().polish(self._dot)

    @staticmethod
    def _resolve_display(info: LicenseInfo) -> tuple[str, str, str, str]:
        """Return (label_text, tone, state_str, tooltip)."""
        state = info.state
        if state == LicenseState.LICENSED_ACTIVE:
            exp = info.license_expires_at
            days_left = (exp - __import__("datetime").date.today()).days if exp else 0
            if days_left <= 30:
                return (
                    f"Licensed · {days_left}d",
                    "warning",
                    "licensed_active",
                    f"License active — expires in {days_left} day(s).\nClick to manage.",
                )
            return (
                "Licensed",
                "success",
                "licensed_active",
                f"License active — expires {exp.isoformat() if exp else ''}.\nClick to manage.",
            )
        if state == LicenseState.LICENSED_EXPIRED:
            return (
                "Expired",
                "danger",
                "licensed_expired",
                "Your license has expired. Click to renew.",
            )
        if state == LicenseState.TRIAL_ACTIVE:
            d = info.trial_days_remaining
            tone = "warning" if d <= 7 else "neutral"
            return (
                f"Trial · {d}d",
                tone,
                "trial_active",
                f"Trial mode — {d} day(s) remaining.\nClick to activate a license.",
            )
        # TRIAL_EXPIRED
        return (
            "Activate",
            "danger",
            "trial_expired",
            "Trial expired — activate a license to continue.\nClick to activate.",
        )
