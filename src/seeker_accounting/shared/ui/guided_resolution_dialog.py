from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.platform.exceptions.error_resolution import (
    GuidedResolution,
    GuidedResolutionAction,
    GuidedResolutionSeverity,
)


class GuidedResolutionDialog(QDialog):
    """Reusable dialog for guided prerequisite/workflow blocker resolutions."""

    def __init__(self, resolution: GuidedResolution, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._resolution = resolution
        self._selected_action: GuidedResolutionAction | None = None

        self.setObjectName("GuidedResolutionDialog")
        self.setModal(True)
        self.setWindowTitle(resolution.title)
        self.resize(560, 360)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(20, 18, 20, 16)
        root_layout.setSpacing(14)

        root_layout.addWidget(self._build_header_card())
        root_layout.addWidget(self._build_message_card())

        details_card = self._build_details_card()
        if details_card is not None:
            root_layout.addWidget(details_card)

        root_layout.addStretch(1)
        root_layout.addLayout(self._build_action_row())

    @property
    def selected_action(self) -> GuidedResolutionAction | None:
        return self._selected_action

    def _build_header_card(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("GuidedResolutionHeaderCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        severity_chip = QLabel(self._severity_label(self._resolution.severity), card)
        severity_chip.setProperty("chipTone", self._severity_chip_tone(self._resolution.severity))
        severity_chip.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        layout.addWidget(severity_chip, alignment=Qt.AlignmentFlag.AlignLeft)

        title = QLabel(self._resolution.title, card)
        title.setObjectName("DialogSectionTitle")
        title.setWordWrap(True)
        layout.addWidget(title)
        return card

    def _build_message_card(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        message = QLabel(self._resolution.message, card)
        message.setObjectName("DialogSectionSummary")
        message.setWordWrap(True)
        layout.addWidget(message)

        if self._resolution.details:
            details = QLabel(self._resolution.details, card)
            details.setObjectName("PageSummary")
            details.setWordWrap(True)
            layout.addWidget(details)

        return card

    def _build_details_card(self) -> QWidget | None:
        if not self._resolution.debug_details:
            return None

        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)

        toggle = QToolButton(card)
        toggle.setObjectName("GuidedResolutionDetailsToggle")
        toggle.setCheckable(True)
        toggle.setChecked(False)
        toggle.setText("Technical details")
        toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        layout.addWidget(toggle, alignment=Qt.AlignmentFlag.AlignLeft)

        details_text = QTextEdit(card)
        details_text.setObjectName("GuidedResolutionDetailsText")
        details_text.setReadOnly(True)
        details_text.setPlainText(self._resolution.debug_details)
        details_text.setVisible(False)
        details_text.setMinimumHeight(90)
        layout.addWidget(details_text)

        toggle.toggled.connect(details_text.setVisible)
        return card

    def _build_action_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addStretch(1)

        actions = self._resolution.actions or [GuidedResolutionAction(action_id="dismiss", label="Close")]

        for action in actions:
            button = QPushButton(action.label, self)
            button.clicked.connect(lambda checked=False, selected=action: self._on_action(selected))
            if action is actions[0]:
                button.setProperty("role", "primary")
                button.setDefault(True)
            row.addWidget(button)

        return row

    def _on_action(self, action: GuidedResolutionAction) -> None:
        self._selected_action = action
        if action.close_dialog:
            self.accept()

    def _severity_label(self, severity: GuidedResolutionSeverity) -> str:
        if severity is GuidedResolutionSeverity.CRITICAL:
            return "Critical"
        if severity is GuidedResolutionSeverity.ERROR:
            return "Action Needed"
        if severity is GuidedResolutionSeverity.WARNING:
            return "Prerequisite"
        return "Information"

    def _severity_chip_tone(self, severity: GuidedResolutionSeverity) -> str:
        if severity in (GuidedResolutionSeverity.CRITICAL, GuidedResolutionSeverity.ERROR):
            return "warning"
        if severity is GuidedResolutionSeverity.WARNING:
            return "info"
        return "neutral"
