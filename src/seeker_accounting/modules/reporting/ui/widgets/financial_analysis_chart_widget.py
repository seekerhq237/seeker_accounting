from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from seeker_accounting.modules.reporting.dto.financial_analysis_chart_dto import (
    FinancialAnalysisViewDTO,
)
from seeker_accounting.shared.ui.styles.palette import ThemePalette
from seeker_accounting.shared.ui.styles.theme_manager import ThemeManager

_ZERO = Decimal("0.00")


class FinancialAnalysisChartWidget(QWidget):
    """Restrained, clickable accounting chart surface for reporting views."""

    point_activated = Signal(str)

    _LEFT_MARGIN = 84
    _RIGHT_MARGIN = 20
    _TOP_MARGIN = 62
    _BOTTOM_MARGIN = 54

    def __init__(
        self,
        theme_manager: ThemeManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._theme_manager = theme_manager
        self._palette = theme_manager.current_palette
        self._view: FinancialAnalysisViewDTO | None = None
        self._hit_regions: list[tuple[QRectF, str]] = []
        self.setMinimumHeight(280)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._theme_manager.theme_changed.connect(self._on_theme_changed)

    def set_view(self, view_dto: FinancialAnalysisViewDTO | None) -> None:
        self._view = view_dto
        self._hit_regions.clear()
        self.update()

    def paintEvent(self, event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(self._palette.workspace_surface))

        if self._view is None or not self._view.series:
            self._draw_empty_state(painter)
            painter.end()
            return

        chart_rect = self._chart_rect()
        if chart_rect.width() <= 1 or chart_rect.height() <= 1:
            painter.end()
            return

        self._draw_title(painter)
        min_value, max_value = self._value_range()
        self._draw_grid(painter, chart_rect, min_value, max_value)
        self._hit_regions.clear()

        if self._view.chart_type == "grouped_bar":
            self._draw_grouped_bar_chart(painter, chart_rect, min_value, max_value)
        else:
            self._draw_line_chart(painter, chart_rect, min_value, max_value)

        self._draw_legend(painter)
        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        position = event.position()
        for rect, detail_key in self._hit_regions:
            if rect.contains(position):
                self.point_activated.emit(detail_key)
                return
        super().mousePressEvent(event)

    def _on_theme_changed(self, theme_name: str) -> None:  # noqa: ARG002
        self._palette = self._theme_manager.current_palette
        self.update()

    def _draw_empty_state(self, painter: QPainter) -> None:
        painter.setPen(QColor(self._palette.text_secondary))
        painter.drawText(
            self.rect(),
            Qt.AlignmentFlag.AlignCenter,
            "No chartable data is available for the selected filters.",
        )

    def _draw_title(self, painter: QPainter) -> None:
        if self._view is None:
            return
        title_font = painter.font()
        title_font.setPointSize(title_font.pointSize() + 2)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor(self._palette.text_primary))
        painter.drawText(
            QRectF(12, 10, self.width() - 24, 24),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self._view.title,
        )

        subtitle_font = painter.font()
        subtitle_font.setPointSize(max(9, subtitle_font.pointSize() - 2))
        subtitle_font.setBold(False)
        painter.setFont(subtitle_font)
        painter.setPen(QColor(self._palette.text_secondary))
        painter.drawText(
            QRectF(12, 34, self.width() - 24, 20),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self._view.subtitle,
        )

    def _draw_legend(self, painter: QPainter) -> None:
        if self._view is None:
            return
        x = 12.0
        y = self.height() - 24.0
        font = painter.font()
        font.setPointSize(max(8, font.pointSize() - 1))
        painter.setFont(font)
        for series in self._view.series:
            color = self._series_color(series.color_name)
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(QRectF(x, y - 8, 10, 10), 2, 2)
            painter.setPen(QColor(self._palette.text_secondary))
            painter.drawText(
                QRectF(x + 16, y - 10, 160, 14),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                series.label,
            )
            x += 132

    def _draw_grid(
        self,
        painter: QPainter,
        rect: QRectF,
        min_value: Decimal,
        max_value: Decimal,
    ) -> None:
        baseline_y = self._value_to_y(_ZERO, rect, min_value, max_value)
        painter.setPen(QPen(QColor(self._palette.border_strong), 1.0))
        painter.drawLine(QPointF(rect.left(), baseline_y), QPointF(rect.right(), baseline_y))

        font = painter.font()
        font.setPointSize(max(8, font.pointSize() - 1))
        painter.setFont(font)

        steps = 5
        for step in range(steps + 1):
            ratio = step / steps
            value = max_value - (max_value - min_value) * Decimal(str(ratio))
            y = rect.top() + rect.height() * ratio
            painter.setPen(QPen(QColor(self._palette.divider_subtle), 1.0))
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            painter.setPen(QColor(self._palette.text_secondary))
            painter.drawText(
                QRectF(0, y - 10, self._LEFT_MARGIN - 8, 20),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                self._format_axis_amount(value),
            )

        painter.setPen(QPen(QColor(self._palette.border_default), 1.0))
        painter.drawRect(rect)

    def _draw_line_chart(
        self,
        painter: QPainter,
        rect: QRectF,
        min_value: Decimal,
        max_value: Decimal,
    ) -> None:
        assert self._view is not None
        categories = [point.label for point in self._view.series[0].points]
        if not categories:
            self._draw_empty_state(painter)
            return

        step_x = rect.width() / max(1, len(categories) - 1)
        for index, label in enumerate(categories):
            x = rect.left() + step_x * index
            self._draw_x_label(painter, x, rect.bottom() + 8, label, max_width=96)

        for series in self._view.series:
            if not series.points:
                continue
            color = self._series_color(series.color_name)
            pen = QPen(color, 2.4)
            painter.setPen(pen)
            path = QPainterPath()
            point_positions: list[tuple[QPointF, str | None]] = []
            for index, point in enumerate(series.points):
                x = rect.left() + step_x * index
                y = self._value_to_y(point.value, rect, min_value, max_value)
                qt_point = QPointF(x, y)
                if index == 0:
                    path.moveTo(qt_point)
                else:
                    path.lineTo(qt_point)
                point_positions.append((qt_point, point.detail_key))
            painter.drawPath(path)

            for qt_point, detail_key in point_positions:
                painter.setBrush(color)
                painter.setPen(QPen(QColor(self._palette.workspace_surface), 2.0))
                marker = QRectF(qt_point.x() - 4.5, qt_point.y() - 4.5, 9.0, 9.0)
                painter.drawEllipse(marker)
                if detail_key:
                    self._hit_regions.append((QRectF(qt_point.x() - 9, qt_point.y() - 9, 18, 18), detail_key))

    def _draw_grouped_bar_chart(
        self,
        painter: QPainter,
        rect: QRectF,
        min_value: Decimal,
        max_value: Decimal,
    ) -> None:
        assert self._view is not None
        categories = [point.label for point in self._view.series[0].points]
        if not categories:
            self._draw_empty_state(painter)
            return

        group_width = rect.width() / max(1, len(categories))
        series_count = max(1, len(self._view.series))
        bar_width = min(40.0, (group_width * 0.72) / series_count)
        baseline_y = self._value_to_y(_ZERO, rect, min_value, max_value)

        for category_index, label in enumerate(categories):
            group_left = rect.left() + category_index * group_width
            painter.setPen(QPen(QColor(self._palette.divider_subtle), 1.0))
            painter.drawLine(
                QPointF(group_left + group_width / 2, rect.top()),
                QPointF(group_left + group_width / 2, rect.bottom()),
            )
            self._draw_x_label(
                painter,
                group_left + group_width / 2,
                rect.bottom() + 8,
                label,
                max_width=max(76, int(group_width) - 6),
            )

            used_width = bar_width * series_count
            start_x = group_left + (group_width - used_width) / 2
            for series_index, series in enumerate(self._view.series):
                if category_index >= len(series.points):
                    continue
                point = series.points[category_index]
                x = start_x + series_index * bar_width
                y = self._value_to_y(point.value, rect, min_value, max_value)
                top = min(y, baseline_y)
                height = max(2.0, abs(baseline_y - y))
                bar_rect = QRectF(x + 3, top, max(6.0, bar_width - 6), height)
                color = self._series_color(series.color_name)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(color)
                painter.drawRoundedRect(bar_rect, 3, 3)
                if point.detail_key:
                    self._hit_regions.append((bar_rect, point.detail_key))

    def _draw_x_label(
        self,
        painter: QPainter,
        x_center: float,
        y_top: float,
        label: str,
        *,
        max_width: int,
    ) -> None:
        painter.setPen(QColor(self._palette.text_secondary))
        painter.drawText(
            QRectF(x_center - max_width / 2, y_top, max_width, 30),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            label,
        )

    def _chart_rect(self) -> QRectF:
        return QRectF(
            self._LEFT_MARGIN,
            self._TOP_MARGIN,
            max(1.0, self.width() - self._LEFT_MARGIN - self._RIGHT_MARGIN),
            max(1.0, self.height() - self._TOP_MARGIN - self._BOTTOM_MARGIN),
        )

    def _value_range(self) -> tuple[Decimal, Decimal]:
        assert self._view is not None
        values = [point.value for series in self._view.series for point in series.points]
        if not values:
            return _ZERO, Decimal("1.00")
        min_value = min(values + [_ZERO])
        max_value = max(values + [_ZERO])
        if min_value == max_value:
            if max_value == _ZERO:
                return Decimal("-1.00"), Decimal("1.00")
            padding = abs(max_value) * Decimal("0.15")
            return (min_value - padding, max_value + padding)
        spread = max_value - min_value
        padding = spread * Decimal("0.10")
        return (min_value - padding, max_value + padding)

    def _value_to_y(
        self,
        value: Decimal,
        rect: QRectF,
        min_value: Decimal,
        max_value: Decimal,
    ) -> float:
        if max_value == min_value:
            return rect.bottom()
        ratio = float((value - min_value) / (max_value - min_value))
        return rect.bottom() - ratio * rect.height()

    def _series_color(self, color_name: str) -> QColor:
        mapping = {
            "accent": self._palette.accent,
            "success": self._palette.success,
            "danger": self._palette.danger,
            "warning": self._palette.warning,
            "info": self._palette.info,
        }
        return QColor(mapping.get(color_name, self._palette.accent))

    @staticmethod
    def _format_axis_amount(value: Decimal) -> str:
        abs_value = abs(value)
        if abs_value >= Decimal("1000000"):
            return f"{(value / Decimal('1000000')):,.1f}M"
        if abs_value >= Decimal("1000"):
            return f"{(value / Decimal('1000')):,.1f}K"
        return f"{value:,.0f}"
