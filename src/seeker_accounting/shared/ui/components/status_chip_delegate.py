"""StatusChipDelegate — paints :class:`StatusChip`-style pills inside table cells.

Unlike a widget-embedded approach, this delegate paints the chip directly
into the cell rectangle, which keeps scrolling fast and avoids per-row
widget overhead.

Data model contract:
    Display role (or ``role`` argument) — the status text (str).
    Optional ``family_role`` — when set and non-empty on the model, the
    returned string overrides the semantic-map lookup.
"""
from __future__ import annotations

from PySide6.QtCore import QModelIndex, QRect, QSize, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QWidget,
)

from seeker_accounting.shared.ui.components.status_chip import (
    _active_palette,
    _bg_color,
    _border_color,
    _dot_color,
    _text_color,
    _format_label,
    resolve_status_family,
)
from seeker_accounting.shared.ui.styles.tokens import DEFAULT_TOKENS

_DEFAULT_CELL_PADDING_H = 10


def _cell_padding_h() -> int:
    return getattr(DEFAULT_TOKENS.sizes, "data_table_cell_padding_h", _DEFAULT_CELL_PADDING_H)


class StatusChipDelegate(QStyledItemDelegate):
    """Paint a status chip directly inside a table cell."""

    def __init__(
        self,
        *,
        role: int = int(Qt.ItemDataRole.DisplayRole),
        family_role: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._role = role
        self._family_role = family_role

    # -- helpers ----------------------------------------------------------

    def _resolve(self, index: QModelIndex) -> tuple[str | None, str, str]:
        """Return ``(raw_status, family, label)`` for a model index."""
        raw = index.data(self._role)
        status = str(raw) if raw not in (None, "") else None

        family: str | None = None
        if self._family_role is not None:
            override = index.data(self._family_role)
            if isinstance(override, str) and override.strip():
                family = override.strip().lower()

        if family is None:
            family = resolve_status_family(status)

        return status, family, _format_label(status)

    # -- paint ------------------------------------------------------------

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        # We paint everything ourselves — clear the default text so the
        # base style does not draw it underneath.
        opt.text = ""

        sizes = DEFAULT_TOKENS.sizes
        palette = _active_palette()

        painter.save()
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            # Selection background first.
            if opt.state & QStyle.StateFlag.State_Selected:
                painter.fillRect(opt.rect, opt.palette.highlight())

            _, family, label = self._resolve(index)

            bg = QColor(_bg_color(palette, family))
            border = QColor(_border_color(palette, family))
            text_col = QColor(_text_color(palette, family))
            dot_col = QColor(_dot_color(palette, family))

            # Compute chip rect inside the cell.
            cell_pad = _cell_padding_h()
            fm = QFontMetrics(opt.font)
            text_w = fm.horizontalAdvance(label)
            gap = 6
            chip_w = (
                sizes.chip_padding_h
                + sizes.chip_dot_size
                + gap
                + text_w
                + sizes.chip_padding_h
            )
            chip_h = sizes.chip_height

            x = opt.rect.left() + cell_pad
            y = opt.rect.center().y() - chip_h // 2
            chip_rect = QRect(x, y, chip_w, chip_h)

            # Background pill.
            painter.setPen(QPen(border, 1))
            painter.setBrush(bg)
            radius = sizes.chip_radius
            painter.drawRoundedRect(chip_rect, radius, radius)

            # Dot.
            dot_size = sizes.chip_dot_size
            dot_rect = QRect(
                chip_rect.left() + sizes.chip_padding_h,
                chip_rect.center().y() - dot_size // 2,
                dot_size,
                dot_size,
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(dot_col)
            painter.drawEllipse(dot_rect)

            # Label text.
            text_left = dot_rect.right() + 1 + gap
            text_rect = QRect(
                text_left,
                chip_rect.top(),
                chip_rect.right() - text_left - sizes.chip_padding_h + 1,
                chip_rect.height(),
            )
            painter.setPen(QPen(text_col))
            painter.setFont(opt.font)
            painter.drawText(
                text_rect,
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                label,
            )
        finally:
            painter.restore()

    # -- sizing -----------------------------------------------------------

    def sizeHint(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> QSize:
        sizes = DEFAULT_TOKENS.sizes
        fm = QFontMetrics(option.font)
        _, _, label = self._resolve(index)
        text_w = fm.horizontalAdvance(label)
        gap = 6
        chip_w = (
            sizes.chip_padding_h
            + sizes.chip_dot_size
            + gap
            + text_w
            + sizes.chip_padding_h
        )
        cell_pad = _cell_padding_h()
        width = chip_w + 2 * cell_pad

        base_h = super().sizeHint(option, index).height()
        height = max(sizes.chip_height + 4, base_h)
        return QSize(width, height)


# ──────────────────────────────────────────────────────────────────────
# Convenience helper
# ──────────────────────────────────────────────────────────────────────


def apply_status_chip_to_column(
    view: QTableView,
    column: int,
    *,
    role: int = int(Qt.ItemDataRole.DisplayRole),
    family_role: int | None = None,
) -> StatusChipDelegate:
    """Install a :class:`StatusChipDelegate` on ``column`` of ``view``.

    Returns the delegate so the caller can keep a reference (Qt does not
    take ownership and a discarded delegate would be garbage-collected).
    """
    delegate = StatusChipDelegate(role=role, family_role=family_role, parent=view)
    view.setItemDelegateForColumn(column, delegate)
    return delegate
