from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.reporting.dto.ratio_analysis_dto import RatioResultDTO
from seeker_accounting.modules.reporting.ui.widgets.mini_trend_chart import MiniTrendChart
from seeker_accounting.shared.ui.styles.theme_manager import ThemeManager


class RatioCard(QFrame):
    """Executive-style ratio card with comparison and sparkline."""

    activated = Signal(str)

    def __init__(
        self,
        theme_manager: ThemeManager,
        ratio: RatioResultDTO,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._ratio = ratio
        self.setObjectName("AnalysisRatioCard")
        self.setFrameShape(QFrame.Shape.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        top_row = QWidget(self)
        top_layout = QHBoxLayout(top_row)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(8)

        title = QLabel(ratio.label, top_row)
        title.setObjectName("AnalysisMetricLabel")
        title.setWordWrap(True)
        top_layout.addWidget(title, 1)

        status = QLabel(ratio.status_label, top_row)
        status.setProperty("chipTone", self._chip_tone(ratio.status_code))
        top_layout.addWidget(status, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(top_row)

        value = QLabel(ratio.display_value, self)
        value.setObjectName("AnalysisMetricValue")
        layout.addWidget(value)

        comparison = QLabel(self._comparison_text(ratio), self)
        comparison.setObjectName("AnalysisMetricMeta")
        comparison.setWordWrap(True)
        layout.addWidget(comparison)

        self._chart = MiniTrendChart(theme_manager, self)
        self._chart.set_points(ratio.trend_points, self._chart_color(ratio.status_code))
        layout.addWidget(self._chart)

        button = QPushButton("View basis", self)
        button.setProperty("variant", "ghost")
        button.clicked.connect(self._emit_activation)
        layout.addWidget(button, 0, Qt.AlignmentFlag.AlignLeft)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self._emit_activation()
        super().mouseDoubleClickEvent(event)

    def _emit_activation(self) -> None:
        if self._ratio.detail_key:
            self.activated.emit(self._ratio.detail_key)

    @staticmethod
    def _comparison_text(ratio: RatioResultDTO) -> str:
        if ratio.unavailable_reason:
            return ratio.unavailable_reason
        parts = []
        if ratio.prior_display_value:
            parts.append(f"Prior: {ratio.prior_display_value}")
        if ratio.change_label:
            parts.append(f"Change: {ratio.change_label}")
        return " | ".join(parts) if parts else "Current-period observation"

    @staticmethod
    def _chip_tone(status_code: str) -> str:
        return {
            "success": "success",
            "warning": "warning",
            "danger": "danger",
            "unavailable": "neutral",
        }.get(status_code, "info")

    @staticmethod
    def _chart_color(status_code: str) -> str:
        return {
            "success": "success",
            "warning": "warning",
            "danger": "danger",
        }.get(status_code, "accent")
