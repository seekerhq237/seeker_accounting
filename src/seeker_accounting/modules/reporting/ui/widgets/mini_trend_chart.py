from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from seeker_accounting.shared.ui.styles.theme_manager import ThemeManager

_ZERO = Decimal("0.00")


class MiniTrendChart(QWidget):
    """Compact sparkline-style chart for analysis cards and detail panels."""

    def __init__(
        self,
        theme_manager: ThemeManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._theme_manager = theme_manager
        self._palette = theme_manager.current_palette
        self._points: tuple[object, ...] = ()
        self._color_name = "accent"
        self.setMinimumHeight(42)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._theme_manager.theme_changed.connect(self._on_theme_changed)

    def set_points(self, points: tuple[object, ...], color_name: str = "accent") -> None:
        self._points = points
        self._color_name = color_name
        self.update()

    def paintEvent(self, event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        if len(self._points) < 2:
            self._draw_empty(painter)
            painter.end()
            return

        chart_rect = QRectF(4, 6, max(1.0, self.width() - 8), max(1.0, self.height() - 12))
        values = [self._value(point) for point in self._points if self._value(point) is not None]
        if len(values) < 2:
            self._draw_empty(painter)
            painter.end()
            return

        min_value = min(values)
        max_value = max(values)
        if min_value == max_value:
            max_value += Decimal("1.00")

        path = QPainterPath()
        step_x = chart_rect.width() / max(1, len(self._points) - 1)
        for index, point in enumerate(self._points):
            value = self._value(point)
            if value is None:
                continue
            x = chart_rect.left() + step_x * index
            ratio = float((value - min_value) / (max_value - min_value))
            y = chart_rect.bottom() - ratio * chart_rect.height()
            if path.isEmpty():
                path.moveTo(QPointF(x, y))
            else:
                path.lineTo(QPointF(x, y))

        painter.setPen(QPen(QColor(self._series_color(self._color_name)), 2.0))
        painter.drawPath(path)
        painter.end()

    def _draw_empty(self, painter: QPainter) -> None:
        pen = QPen(QColor(self._palette.border_default), 1.0, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawLine(4, self.height() // 2, self.width() - 4, self.height() // 2)

    def _on_theme_changed(self, theme_name: str) -> None:  # noqa: ARG002
        self._palette = self._theme_manager.current_palette
        self.update()

    def _series_color(self, color_name: str) -> str:
        mapping = {
            "accent": self._palette.accent,
            "success": self._palette.success,
            "danger": self._palette.danger,
            "warning": self._palette.warning,
            "info": self._palette.info,
        }
        return mapping.get(color_name, self._palette.accent)

    @staticmethod
    def _value(point: object) -> Decimal | None:
        value = getattr(point, "value", None)
        if isinstance(value, Decimal):
            return value
        return None
