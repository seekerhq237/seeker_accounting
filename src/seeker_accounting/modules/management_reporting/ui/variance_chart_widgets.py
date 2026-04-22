"""QPainter-based chart widgets for project variance and cost analysis.

These are lightweight, theme-aware chart components used by the variance
analysis and contract summary pages.  No external charting library is needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from seeker_accounting.shared.ui.styles.palette import ThemePalette


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_ZERO = Decimal(0)


def _dec_float(v: Decimal) -> float:
    return float(v)


def _format_amount_short(v: Decimal) -> str:
    """Compact display: 1.2M / 345K / 1,200."""
    abs_v = abs(v)
    sign = "-" if v < 0 else ""
    if abs_v >= 1_000_000:
        return f"{sign}{_dec_float(abs_v / 1_000_000):.1f}M"
    if abs_v >= 10_000:
        return f"{sign}{_dec_float(abs_v / 1_000):.0f}K"
    if abs_v >= 1_000:
        return f"{sign}{_dec_float(abs_v / 1_000):.1f}K"
    return f"{sign}{_dec_float(abs_v):,.0f}"


def _lerp_color(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
        int(a.alpha() + (b.alpha() - a.alpha()) * t),
    )


# ---------------------------------------------------------------------------
# Chart data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class WaterfallSegment:
    label: str
    value: Decimal
    is_total: bool = False


@dataclass(frozen=True, slots=True)
class HBarItem:
    label: str
    value: Decimal
    secondary_value: Decimal | None = None  # optional commitment overlay


@dataclass(frozen=True, slots=True)
class TrendPoint:
    label: str
    actual_cumulative: Decimal
    revenue_cumulative: Decimal


# ---------------------------------------------------------------------------
# Base chart widget
# ---------------------------------------------------------------------------


class _BaseChart(QWidget):
    """Lightweight base for all chart widgets."""

    _LEFT_MARGIN = 70
    _RIGHT_MARGIN = 20
    _TOP_MARGIN = 30
    _BOTTOM_MARGIN = 36

    def __init__(self, palette: ThemePalette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._palette = palette
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(180)

    def update_palette(self, palette: ThemePalette) -> None:
        self._palette = palette
        self.update()

    def _chart_rect(self) -> QRectF:
        return QRectF(
            self._LEFT_MARGIN,
            self._TOP_MARGIN,
            max(1, self.width() - self._LEFT_MARGIN - self._RIGHT_MARGIN),
            max(1, self.height() - self._TOP_MARGIN - self._BOTTOM_MARGIN),
        )

    def _axis_pen(self) -> QPen:
        return QPen(QColor(self._palette.border_default), 1)

    def _label_font(self) -> QFont:
        f = QFont("Segoe UI", 10)
        f.setWeight(QFont.Weight.Normal)
        return f

    def _title_font(self) -> QFont:
        f = QFont("Segoe UI", 11)
        f.setWeight(QFont.Weight.DemiBold)
        return f

    def _draw_title(self, painter: QPainter, title: str) -> None:
        painter.setFont(self._title_font())
        painter.setPen(QColor(self._palette.text_primary))
        painter.drawText(QRectF(8, 4, self.width() - 16, 24), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title)

    def _draw_y_grid(self, painter: QPainter, rect: QRectF, max_val: float, steps: int = 5) -> None:
        painter.setPen(self._axis_pen())
        painter.setFont(self._label_font())
        for i in range(steps + 1):
            y = rect.bottom() - (rect.height() * i / steps)
            val = max_val * i / steps
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            label = _format_amount_short(Decimal(str(val)))
            painter.setPen(QColor(self._palette.text_secondary))
            painter.drawText(
                QRectF(0, y - 10, self._LEFT_MARGIN - 6, 20),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                label,
            )
            painter.setPen(self._axis_pen())


# ---------------------------------------------------------------------------
# Waterfall / bridge chart  (Budget → Actuals → Commitments → Remaining)
# ---------------------------------------------------------------------------


class WaterfallChart(_BaseChart):
    """Vertical waterfall chart for budget control bridge."""

    def __init__(self, palette: ThemePalette, parent: QWidget | None = None) -> None:
        super().__init__(palette, parent)
        self._title = "Budget Control Bridge"
        self._segments: list[WaterfallSegment] = []

    def set_data(self, segments: list[WaterfallSegment], title: str | None = None) -> None:
        self._segments = segments
        if title is not None:
            self._title = title
        self.update()

    def paintEvent(self, event: object) -> None:  # noqa: N802
        if not self._segments:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._draw_title(painter, self._title)

        rect = self._chart_rect()
        n = len(self._segments)
        if n == 0:
            painter.end()
            return

        # Determine value range
        running = _ZERO
        positions: list[tuple[float, float]] = []  # (top, bottom) for each bar
        max_extent = _ZERO
        for seg in self._segments:
            if seg.is_total:
                top = max(seg.value, _ZERO)
                bot = min(seg.value, _ZERO)
                positions.append((_dec_float(top), _dec_float(bot)))
                max_extent = max(max_extent, abs(seg.value))
            else:
                start = running
                running = running + seg.value
                top = max(start, running)
                bot = min(start, running)
                positions.append((_dec_float(top), _dec_float(bot)))
                max_extent = max(max_extent, abs(top), abs(bot))
        if max_extent == 0:
            max_extent = Decimal(1)

        max_val = _dec_float(max_extent) * 1.15
        self._draw_y_grid(painter, rect, max_val)

        bar_w = rect.width() / n
        gap = max(2.0, bar_w * 0.2)
        accent = QColor(self._palette.accent)
        success = QColor(self._palette.success)
        danger = QColor(self._palette.danger)
        warning = QColor(self._palette.warning)

        for i, (seg, (top_v, bot_v)) in enumerate(zip(self._segments, positions)):
            x = rect.left() + i * bar_w + gap / 2
            w = bar_w - gap

            y_top = rect.bottom() - (top_v / max_val) * rect.height()
            y_bot = rect.bottom() - (bot_v / max_val) * rect.height()
            bar_h = max(1.0, y_bot - y_top)

            if seg.is_total:
                color = accent
            elif seg.value > 0:
                color = success
            elif seg.value < 0:
                color = danger
            else:
                color = warning

            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(QRectF(x, y_top, w, bar_h), 3, 3)

            # Label below
            painter.setPen(QColor(self._palette.text_secondary))
            painter.setFont(self._label_font())
            label_rect = QRectF(x - 4, rect.bottom() + 4, w + 8, 20)
            painter.drawText(label_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, seg.label)

            # Value on bar
            val_label = _format_amount_short(seg.value)
            painter.setPen(QColor(self._palette.text_primary))
            val_rect = QRectF(x, y_top - 16, w, 14)
            painter.drawText(val_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom, val_label)

        painter.end()


# ---------------------------------------------------------------------------
# Horizontal bar chart  (variance by cost code / by job)
# ---------------------------------------------------------------------------


class HorizontalBarChart(_BaseChart):
    """Horizontal bar chart for dimensional variance breakdown."""

    _LEFT_MARGIN = 120
    _BOTTOM_MARGIN = 24

    def __init__(self, palette: ThemePalette, parent: QWidget | None = None) -> None:
        super().__init__(palette, parent)
        self._title = "Variance by Dimension"
        self._items: list[HBarItem] = []

    def set_data(self, items: list[HBarItem], title: str | None = None) -> None:
        self._items = items
        if title is not None:
            self._title = title
        self.update()

    def paintEvent(self, event: object) -> None:  # noqa: N802
        if not self._items:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._draw_title(painter, self._title)

        rect = self._chart_rect()
        n = len(self._items)
        if n == 0:
            painter.end()
            return

        max_val = max(abs(_dec_float(it.value)) for it in self._items)
        if self._items and any(it.secondary_value is not None for it in self._items):
            max_val = max(max_val, max(
                abs(_dec_float(it.secondary_value)) for it in self._items if it.secondary_value is not None
            ))
        if max_val == 0:
            max_val = 1.0

        bar_h = rect.height() / n
        gap = max(2.0, bar_h * 0.15)
        success = QColor(self._palette.success)
        danger = QColor(self._palette.danger)
        accent_soft = QColor(self._palette.accent_soft_strong)

        for i, item in enumerate(self._items):
            y = rect.top() + i * bar_h + gap / 2
            h = bar_h - gap
            val = _dec_float(item.value)
            w = (abs(val) / max_val) * rect.width() * 0.85
            color = success if val >= 0 else danger

            # Optional commitment overlay
            if item.secondary_value is not None:
                sec_val = abs(_dec_float(item.secondary_value))
                sec_w = (sec_val / max_val) * rect.width() * 0.85
                painter.setBrush(accent_soft)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(QRectF(rect.left(), y, sec_w, h), 3, 3)

            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(QRectF(rect.left(), y, w, h), 3, 3)

            # Label on left
            painter.setPen(QColor(self._palette.text_primary))
            painter.setFont(self._label_font())
            label_rect = QRectF(4, y, self._LEFT_MARGIN - 8, h)
            painter.drawText(
                label_rect,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                item.label[:18],
            )

            # Value on right of bar
            painter.setPen(QColor(self._palette.text_secondary))
            val_rect = QRectF(rect.left() + w + 4, y, 60, h)
            painter.drawText(
                val_rect,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                _format_amount_short(item.value),
            )

        painter.end()


# ---------------------------------------------------------------------------
# Trend / burn line chart  (cumulative actual cost + revenue + budget ref)
# ---------------------------------------------------------------------------


class TrendLineChart(_BaseChart):
    """Line chart for cost/revenue trend with optional budget reference line."""

    def __init__(self, palette: ThemePalette, parent: QWidget | None = None) -> None:
        super().__init__(palette, parent)
        self._title = "Cost & Revenue Trend"
        self._points: list[TrendPoint] = []
        self._budget_line: float | None = None

    def set_data(
        self,
        points: list[TrendPoint],
        budget_reference: Decimal | None = None,
        title: str | None = None,
    ) -> None:
        self._points = points
        self._budget_line = _dec_float(budget_reference) if budget_reference is not None else None
        if title is not None:
            self._title = title
        self.update()

    def paintEvent(self, event: object) -> None:  # noqa: N802
        if not self._points:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._draw_title(painter, self._title)

        rect = self._chart_rect()
        n = len(self._points)
        if n < 2:
            painter.end()
            return

        # Determine max value
        vals: list[float] = []
        for p in self._points:
            vals.append(_dec_float(p.actual_cumulative))
            vals.append(_dec_float(p.revenue_cumulative))
        if self._budget_line is not None:
            vals.append(self._budget_line)
        max_val = max(vals) if vals else 1.0
        if max_val <= 0:
            max_val = 1.0
        max_val *= 1.1

        self._draw_y_grid(painter, rect, max_val)

        def x_for(idx: int) -> float:
            return rect.left() + (idx / (n - 1)) * rect.width()

        def y_for(val: float) -> float:
            return rect.bottom() - (val / max_val) * rect.height()

        # Budget reference line (dashed)
        if self._budget_line is not None:
            pen = QPen(QColor(self._palette.warning), 1.5, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            by = y_for(self._budget_line)
            painter.drawLine(QPointF(rect.left(), by), QPointF(rect.right(), by))
            painter.setFont(self._label_font())
            painter.setPen(QColor(self._palette.warning))
            painter.drawText(
                QRectF(rect.right() - 80, by - 16, 78, 14),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
                f"Budget {_format_amount_short(Decimal(str(self._budget_line)))}",
            )

        # Draw actual cost line
        cost_color = QColor(self._palette.danger)
        self._draw_series(painter, rect, n, x_for, y_for, cost_color, [_dec_float(p.actual_cumulative) for p in self._points])

        # Draw revenue line
        rev_color = QColor(self._palette.success)
        self._draw_series(painter, rect, n, x_for, y_for, rev_color, [_dec_float(p.revenue_cumulative) for p in self._points])

        # X-axis labels
        painter.setPen(QColor(self._palette.text_secondary))
        painter.setFont(self._label_font())
        step = max(1, n // 6)
        for i in range(0, n, step):
            lx = x_for(i)
            painter.drawText(
                QRectF(lx - 30, rect.bottom() + 4, 60, 18),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                self._points[i].label,
            )

        # Legend
        self._draw_legend(painter, rect, cost_color, "Actual Cost", rev_color, "Revenue")

        painter.end()

    def _draw_series(
        self,
        painter: QPainter,
        rect: QRectF,
        n: int,
        x_for: object,
        y_for: object,
        color: QColor,
        values: list[float],
    ) -> None:
        pen = QPen(color, 2)
        painter.setPen(pen)
        path = QPainterPath()
        for i, val in enumerate(values):
            px, py = x_for(i), y_for(val)
            if i == 0:
                path.moveTo(px, py)
            else:
                path.lineTo(px, py)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        # Draw dots at data points
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        for i, val in enumerate(values):
            px, py = x_for(i), y_for(val)
            painter.drawEllipse(QPointF(px, py), 3, 3)

    def _draw_legend(
        self,
        painter: QPainter,
        rect: QRectF,
        c1: QColor,
        l1: str,
        c2: QColor,
        l2: str,
    ) -> None:
        painter.setFont(self._label_font())
        lx = rect.right() - 180
        ly = rect.top() - 8
        for color, label, offset in ((c1, l1, 0), (c2, l2, 90)):
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(lx + offset, ly + 5), 4, 4)
            painter.setPen(QColor(self._palette.text_secondary))
            painter.drawText(QRectF(lx + offset + 8, ly - 2, 78, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)


# ---------------------------------------------------------------------------
# Mini sparkline for contract summary
# ---------------------------------------------------------------------------


class MiniSparkline(_BaseChart):
    """Compact sparkline for inline use in contract summary cards."""

    _LEFT_MARGIN = 0
    _RIGHT_MARGIN = 0
    _TOP_MARGIN = 4
    _BOTTOM_MARGIN = 4

    def __init__(self, palette: ThemePalette, parent: QWidget | None = None) -> None:
        super().__init__(palette, parent)
        self._values: list[float] = []
        self.setMinimumHeight(40)
        self.setMaximumHeight(60)

    def set_data(self, values: list[Decimal]) -> None:
        self._values = [_dec_float(v) for v in values]
        self.update()

    def paintEvent(self, event: object) -> None:  # noqa: N802
        if len(self._values) < 2:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self._chart_rect()
        n = len(self._values)
        max_val = max(self._values) or 1.0

        color = QColor(self._palette.accent)
        pen = QPen(color, 1.5)
        painter.setPen(pen)

        path = QPainterPath()
        for i, val in enumerate(self._values):
            px = rect.left() + (i / (n - 1)) * rect.width()
            py = rect.bottom() - (val / max_val) * rect.height()
            if i == 0:
                path.moveTo(px, py)
            else:
                path.lineTo(px, py)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        # Fill area under curve
        fill_path = QPainterPath(path)
        fill_path.lineTo(rect.right(), rect.bottom())
        fill_path.lineTo(rect.left(), rect.bottom())
        fill_path.closeSubpath()
        fill_color = QColor(color)
        fill_color.setAlpha(30)
        painter.setBrush(fill_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(fill_path)

        painter.end()
