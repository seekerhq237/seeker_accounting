from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.reporting.dto.insight_card_dto import InsightCardDTO


class InsightCard(QFrame):
    """Rule-based management insight card with visible numeric basis."""

    activated = Signal(str)

    def __init__(self, card: InsightCardDTO, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._card = card
        self.setObjectName("AnalysisInsightCard")
        self.setFrameShape(QFrame.Shape.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        top_row = QWidget(self)
        top_layout = QHBoxLayout(top_row)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(8)

        title = QLabel(card.title, top_row)
        title.setObjectName("AnalysisInsightTitle")
        title.setWordWrap(True)
        top_layout.addWidget(title, 1)

        severity = QLabel(card.severity_code.title(), top_row)
        severity.setProperty("chipTone", self._chip_tone(card.severity_code))
        top_layout.addWidget(severity)
        layout.addWidget(top_row)

        statement = QLabel(card.statement, self)
        statement.setObjectName("AnalysisInsightBody")
        statement.setWordWrap(True)
        layout.addWidget(statement)

        reason = QLabel(card.why_it_matters, self)
        reason.setObjectName("AnalysisInsightMeta")
        reason.setWordWrap(True)
        layout.addWidget(reason)

        basis_row = QWidget(self)
        basis_layout = QHBoxLayout(basis_row)
        basis_layout.setContentsMargins(0, 0, 0, 0)
        basis_layout.setSpacing(8)
        for item in card.numeric_basis[:4]:
            chip = QLabel(f"{item.label}: {item.value_text}", basis_row)
            chip.setProperty("chipTone", "info")
            chip.setWordWrap(True)
            basis_layout.addWidget(chip)
        basis_layout.addStretch(1)
        layout.addWidget(basis_row)

        if card.comparison_text:
            comparison = QLabel(card.comparison_text, self)
            comparison.setObjectName("AnalysisInsightMeta")
            comparison.setWordWrap(True)
            layout.addWidget(comparison)

        button = QPushButton("Open detail", self)
        button.setProperty("variant", "ghost")
        button.clicked.connect(self._emit_activation)
        layout.addWidget(button)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self._emit_activation()
        super().mouseDoubleClickEvent(event)

    def _emit_activation(self) -> None:
        if self._card.detail_key:
            self.activated.emit(self._card.detail_key)

    @staticmethod
    def _chip_tone(severity_code: str) -> str:
        return {
            "danger": "danger",
            "warning": "warning",
            "success": "success",
        }.get(severity_code, "info")
