from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from seeker_accounting.modules.reporting.dto.interpretation_dto import InterpretationPanelDTO


class InterpretationPanel(QFrame):
    """Compact panel for high-value rule-based interpretations."""

    detail_requested = Signal(str)

    def __init__(self, panel: InterpretationPanelDTO, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("AnalysisInterpretationPanel")
        self.setFrameShape(QFrame.Shape.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        title = QLabel(panel.title, self)
        title.setObjectName("AnalysisSectionTitle")
        layout.addWidget(title)

        if panel.subtitle:
            subtitle = QLabel(panel.subtitle, self)
            subtitle.setObjectName("AnalysisSectionSubtitle")
            subtitle.setWordWrap(True)
            layout.addWidget(subtitle)

        for item in panel.items:
            row = QWidget(self)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(10)

            severity = QLabel(item.severity_code.title(), row)
            severity.setProperty("chipTone", self._chip_tone(item.severity_code))
            row_layout.addWidget(severity, 0)

            text_block = QWidget(row)
            text_layout = QVBoxLayout(text_block)
            text_layout.setContentsMargins(0, 0, 0, 0)
            text_layout.setSpacing(2)
            heading = QLabel(item.title, text_block)
            heading.setObjectName("AnalysisInsightTitle")
            heading.setWordWrap(True)
            text_layout.addWidget(heading)
            body = QLabel(item.message, text_block)
            body.setObjectName("AnalysisInsightBody")
            body.setWordWrap(True)
            text_layout.addWidget(body)
            basis = QLabel(item.basis_text, text_block)
            basis.setObjectName("AnalysisInsightMeta")
            basis.setWordWrap(True)
            text_layout.addWidget(basis)
            row_layout.addWidget(text_block, 1)

            if item.detail_key:
                button = QPushButton("Review", row)
                button.setProperty("variant", "ghost")
                button.clicked.connect(lambda checked=False, key=item.detail_key: self.detail_requested.emit(key))
                row_layout.addWidget(button)
            layout.addWidget(row)

    @staticmethod
    def _chip_tone(severity_code: str) -> str:
        return {
            "danger": "danger",
            "warning": "warning",
            "success": "success",
        }.get(severity_code, "info")
