"""Reusable QStyledItemDelegate subclasses for editable table grids.

Provides:
- ``ComboBoxDelegate``  — dropdown selection with SearchableComboBox editor
- ``NumericDelegate``   — right-aligned decimal display with QLineEdit editor
- ``RowNumberDelegate`` — paint-only row number gutter
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Sequence

from PySide6.QtCore import QModelIndex, QRect, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QLineEdit,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QWidget,
)

from seeker_accounting.shared.ui.searchable_combo_box import SearchableComboBox

# ──────────────────────────────────────────────────────────────────────
# ComboBoxDelegate
# ──────────────────────────────────────────────────────────────────────

_CHEVRON = "\u25BE"  # small down-pointing triangle


class ComboBoxDelegate(QStyledItemDelegate):
    """Delegate that paints selected text + chevron and opens a
    ``SearchableComboBox`` editor on demand.

    Data model contract:
        ``Qt.DisplayRole``  — display text (str)
        ``Qt.UserRole``     — underlying value (int / str / Any)
    """

    def __init__(
        self,
        items: Sequence[tuple[str, Any]] = (),
        placeholder: str = "-- Select --",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._items: list[tuple[str, Any]] = list(items)
        self._placeholder = placeholder

    # -- public refresh ---------------------------------------------------

    def set_items(self, items: Sequence[tuple[str, Any]]) -> None:
        self._items = list(items)

    # -- paint ------------------------------------------------------------

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        # Let the base handle selection highlight / focus rect
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        style = opt.widget.style() if opt.widget else QApplication.style()

        # Draw background (selection, hover, alternating)
        style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, opt, painter, opt.widget)

        painter.save()

        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        is_placeholder = not text or text == self._placeholder

        rect: QRect = opt.rect.adjusted(6, 0, -6, 0)
        chevron_width = 14

        # Text
        text_rect = QRect(rect.left(), rect.top(), rect.width() - chevron_width, rect.height())
        palette = opt.palette

        if is_placeholder:
            pen_color = palette.color(palette.ColorRole.PlaceholderText)
            font = QFont(opt.font)
            font.setItalic(True)
            painter.setFont(font)
            display = self._placeholder
        else:
            if opt.state & QStyle.StateFlag.State_Selected:
                pen_color = palette.color(palette.ColorRole.HighlightedText)
            else:
                pen_color = palette.color(palette.ColorRole.Text)
            display = text

        painter.setPen(QPen(pen_color))
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            painter.fontMetrics().elidedText(display, Qt.TextElideMode.ElideRight, text_rect.width()),
        )

        # Chevron
        chevron_rect = QRect(
            rect.right() - chevron_width, rect.top(), chevron_width, rect.height()
        )
        chevron_color = palette.color(palette.ColorRole.PlaceholderText)
        painter.setPen(QPen(chevron_color))
        painter.setFont(opt.font)
        painter.drawText(chevron_rect, Qt.AlignmentFlag.AlignCenter, _CHEVRON)

        painter.restore()

    # -- editor -----------------------------------------------------------

    def createEditor(
        self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex
    ) -> QWidget:
        editor = SearchableComboBox(parent)
        editor.set_items(self._items, placeholder=self._placeholder)
        editor.setFrame(False)
        # Hide the built-in dropdown arrow button and zero out QComboBox
        # internal padding so the lineEdit text aligns with the delegate's
        # painted text position instead of appearing offset / cropped.
        editor.setStyleSheet(
            "QComboBox { padding-left: 6px; padding-right: 6px; }"
            "QComboBox::drop-down { width: 0px; border: none; }"
        )
        # When the user picks a value, commit immediately
        editor.value_changed.connect(lambda _: self.commitData.emit(editor))
        return editor

    def setEditorData(self, editor: QWidget, index: QModelIndex) -> None:
        if not isinstance(editor, SearchableComboBox):
            return
        value = index.data(Qt.ItemDataRole.UserRole)
        if value is not None:
            editor.set_current_value(value)
        else:
            editor.clear_selection()

    def setModelData(
        self, editor: QWidget, model: Any, index: QModelIndex
    ) -> None:
        if not isinstance(editor, SearchableComboBox):
            return
        value = editor.current_value()
        # Read display text from the source model item — NOT currentText()
        # which returns lineEdit().text() on editable combos (stale search text).
        proxy_idx = editor.model().index(editor.currentIndex(), 0)
        display = proxy_idx.data(Qt.ItemDataRole.DisplayRole) if proxy_idx.isValid() else ""
        model.setData(index, display, Qt.ItemDataRole.DisplayRole)
        model.setData(index, value, Qt.ItemDataRole.UserRole)

    def updateEditorGeometry(
        self, editor: QWidget, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        editor.setGeometry(option.rect)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> Any:
        hint = super().sizeHint(option, index)
        hint.setHeight(max(hint.height(), 28))
        return hint


# ──────────────────────────────────────────────────────────────────────
# NumericDelegate
# ──────────────────────────────────────────────────────────────────────


def _format_number(value: Decimal, max_decimals: int = 2) -> str:
    """Format a decimal with thousands separators, stripping unnecessary trailing zeros.

    Examples: 100 -> "100", 10.50 -> "10.5", 1234.00 -> "1,234", 0.10 -> "0.1"
    """
    formatted = f"{value:,.{max_decimals}f}"
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
    return formatted


class NumericDelegate(QStyledItemDelegate):
    """Right-aligned decimal display with optional QLineEdit editor.

    Data model contract:
        ``Qt.DisplayRole``  — formatted string (e.g. "1,234")
        ``Qt.UserRole``     — raw ``Decimal`` or ``None``
    """

    def __init__(
        self,
        decimals: int = 2,
        read_only: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._decimals = decimals
        self._read_only = read_only

    # -- paint ------------------------------------------------------------

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, opt, painter, opt.widget)

        painter.save()

        raw = index.data(Qt.ItemDataRole.UserRole)
        if raw is not None and raw != "":
            try:
                val = Decimal(str(raw))
                text = _format_number(val, self._decimals)
            except (InvalidOperation, ValueError):
                text = str(raw)
        else:
            text = ""

        rect = opt.rect.adjusted(4, 0, -6, 0)
        palette = opt.palette
        if opt.state & QStyle.StateFlag.State_Selected:
            pen_color = palette.color(palette.ColorRole.HighlightedText)
        else:
            pen_color = palette.color(palette.ColorRole.Text)

        painter.setPen(QPen(pen_color))
        painter.drawText(
            rect,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            text,
        )
        painter.restore()

    # -- editor -----------------------------------------------------------

    def createEditor(
        self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex
    ) -> QWidget | None:
        if self._read_only:
            return None
        editor = QLineEdit(parent)
        editor.setAlignment(Qt.AlignmentFlag.AlignRight)
        editor.setFrame(False)
        # Commit data when the editor loses focus (persistent editor support)
        editor.editingFinished.connect(lambda: self.commitData.emit(editor))
        return editor

    def setEditorData(self, editor: QWidget, index: QModelIndex) -> None:
        if not isinstance(editor, QLineEdit):
            return
        raw = index.data(Qt.ItemDataRole.UserRole)
        if raw is not None:
            editor.setText(str(raw))
        else:
            editor.setText("")

    def setModelData(
        self, editor: QWidget, model: Any, index: QModelIndex
    ) -> None:
        if not isinstance(editor, QLineEdit):
            return
        text = editor.text().replace(",", "").strip()
        if text:
            try:
                value = Decimal(text)
            except InvalidOperation:
                return  # keep old value on garbage input
        else:
            value = None
        fmt = _format_number(value, self._decimals) if value is not None else ""
        model.setData(index, fmt, Qt.ItemDataRole.DisplayRole)
        model.setData(index, value, Qt.ItemDataRole.UserRole)

    def updateEditorGeometry(
        self, editor: QWidget, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        if editor:
            editor.setGeometry(option.rect)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> Any:
        hint = super().sizeHint(option, index)
        hint.setHeight(max(hint.height(), 28))
        return hint


# ──────────────────────────────────────────────────────────────────────
# RowNumberDelegate
# ──────────────────────────────────────────────────────────────────────


class RowNumberDelegate(QStyledItemDelegate):
    """Paint-only delegate that displays ``row + 1`` in muted text."""

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, opt, painter, opt.widget)

        painter.save()

        text = str(index.row() + 1)
        palette = opt.palette
        color = palette.color(palette.ColorRole.PlaceholderText)
        font = QFont(opt.font)
        font.setPointSizeF(font.pointSizeF() * 0.9)
        painter.setFont(font)
        painter.setPen(QPen(color))
        painter.drawText(
            opt.rect,
            Qt.AlignmentFlag.AlignCenter,
            text,
        )
        painter.restore()

    def createEditor(
        self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        return None  # never editable

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> Any:
        hint = super().sizeHint(option, index)
        hint.setHeight(max(hint.height(), 28))
        return hint
