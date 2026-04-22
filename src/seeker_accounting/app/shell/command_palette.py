"""VS Code-style in-window command palette overlay for universal search and navigation.

Activated via Ctrl+F.  Renders as a full-window child overlay with a dim backdrop
and a floating panel at the top-centre — identical to VS Code's command palette.
Provides fuzzy-matched results across navigation pages, action commands, entity
searches (live DB), and reports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

_ROLE_RESULT = Qt.ItemDataRole.UserRole + 1
_ROLE_IS_HEADER = Qt.ItemDataRole.UserRole + 2


@dataclass(frozen=True, slots=True)
class PaletteResult:
    """A single result row in the command palette."""

    category: str
    title: str
    subtitle: str
    icon_hint: str  # category key for icon lookup
    score: float
    action: Callable[[], None]
    keywords: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Custom delegate – renders result rows with rich styling
# ---------------------------------------------------------------------------

class _PaletteItemDelegate(QStyledItemDelegate):
    """Draws palette rows: category headers or result rows with title + subtitle."""

    _ROW_HEIGHT = 34
    _HEADER_HEIGHT = 26

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        if index.data(_ROLE_IS_HEADER):
            return QSize(option.rect.width(), self._HEADER_HEIGHT)
        return QSize(option.rect.width(), self._ROW_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = option.rect
        palette = option.palette  # type: ignore[assignment]
        is_header = index.data(_ROLE_IS_HEADER)
        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)

        if is_header:
            self._paint_header(painter, rect, index.data(Qt.ItemDataRole.DisplayRole), palette)
        else:
            self._paint_result(painter, rect, index, palette, is_selected)

        painter.restore()

    def _paint_header(self, painter: QPainter, rect, text: str, palette) -> None:
        font = QFont(painter.font())
        font.setPixelSize(11)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(QPen(palette.color(palette.ColorRole.PlaceholderText)))
        painter.drawText(
            rect.adjusted(14, 0, 0, 0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            text.upper(),
        )

    def _paint_result(self, painter: QPainter, rect, index, palette, is_selected: bool) -> None:
        result: PaletteResult | None = index.data(_ROLE_RESULT)
        if result is None:
            return

        # Background for selected row.
        if is_selected:
            sel_color = palette.color(palette.ColorRole.Highlight)
            sel_color.setAlpha(40)
            path = QPainterPath()
            path.addRoundedRect(rect.adjusted(4, 1, -4, -1).toRectF(), 6, 6)
            painter.fillPath(path, sel_color)

        # Title.
        title_font = QFont(painter.font())
        title_font.setPixelSize(13)
        title_font.setWeight(QFont.Weight.Medium)
        painter.setFont(title_font)

        title_color = palette.color(palette.ColorRole.HighlightedText) if is_selected else palette.color(palette.ColorRole.Text)
        painter.setPen(QPen(title_color))
        title_rect = rect.adjusted(14, 0, -160, 0)
        fm = QFontMetrics(title_font)
        elided_title = fm.elidedText(result.title, Qt.TextElideMode.ElideRight, title_rect.width())
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided_title)

        # Subtitle.
        sub_font = QFont(painter.font())
        sub_font.setPixelSize(11)
        sub_font.setWeight(QFont.Weight.Normal)
        painter.setFont(sub_font)
        painter.setPen(QPen(palette.color(palette.ColorRole.PlaceholderText)))
        sub_rect = rect.adjusted(14 + fm.horizontalAdvance(elided_title) + 10, 0, -80, 0)
        fm_sub = QFontMetrics(sub_font)
        elided_sub = fm_sub.elidedText(result.subtitle, Qt.TextElideMode.ElideRight, max(sub_rect.width(), 0))
        painter.drawText(sub_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided_sub)

        # Right-aligned category hint.
        hint_font = QFont(painter.font())
        hint_font.setPixelSize(10)
        painter.setFont(hint_font)
        painter.setPen(QPen(palette.color(palette.ColorRole.PlaceholderText)))
        hint_rect = rect.adjusted(rect.width() - 80, 0, -10, 0)
        painter.drawText(hint_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, result.category)


# ---------------------------------------------------------------------------
# CommandPalette overlay widget
# ---------------------------------------------------------------------------

class CommandPalette(QWidget):
    """Full-window in-place overlay with a VS Code-style command palette panel.

    This widget must be a *child* of the shell root frame so it can cover the
    full window.  It paints a translucent dim over its entire area and centres
    a floating panel (``self._panel``) near the top — exactly like VS Code's
    command palette.

    Clicking outside the panel or pressing Escape dismisses the overlay.
    """

    _PANEL_WIDTH = 640
    _PANEL_MAX_HEIGHT = 460
    _INPUT_HEIGHT = 44
    _PANEL_TOP_OFFSET = 56   # px from top of overlay to top of panel

    result_activated = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("CommandPaletteOverlay")

        # Overlay itself must never steal focus — focus belongs to _input.
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.hide()

        self._providers: list[Any] = []

        # ── Panel (the actual visible palette box) ────────────────────────
        self._panel = QFrame(self)
        self._panel.setObjectName("CommandPalette")
        self._panel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._panel.setFixedWidth(self._PANEL_WIDTH)

        shadow = QGraphicsDropShadowEffect(self._panel)
        shadow.setBlurRadius(40)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 80))
        self._panel.setGraphicsEffect(shadow)

        panel_layout = QVBoxLayout(self._panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        # Search input.
        self._input = QLineEdit(self._panel)
        self._input.setObjectName("CommandPaletteInput")
        self._input.setPlaceholderText("Search pages, commands, customers, items, reports…")
        self._input.setFixedHeight(self._INPUT_HEIGHT)
        self._input.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        panel_layout.addWidget(self._input)

        # Separator.
        sep = QFrame(self._panel)
        sep.setObjectName("CommandPaletteSep")
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        panel_layout.addWidget(sep)

        # Results list.
        self._list = QListWidget(self._panel)
        self._list.setObjectName("CommandPaletteList")
        self._list.setItemDelegate(_PaletteItemDelegate(self._list))
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._list.setMouseTracking(True)
        panel_layout.addWidget(self._list, 1)

        # Hint bar.
        hint_bar = QFrame(self._panel)
        hint_bar.setObjectName("CommandPaletteHintBar")
        hint_layout = QHBoxLayout(hint_bar)
        hint_layout.setContentsMargins(14, 4, 14, 6)
        hint_hint = QLabel("↑↓ Navigate   ↵ Open   Esc Close", hint_bar)
        hint_hint.setObjectName("CommandPaletteHintLabel")
        hint_layout.addWidget(hint_hint)
        hint_layout.addStretch()
        panel_layout.addWidget(hint_bar)

        # Debounce timer.
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(120)
        self._debounce.timeout.connect(self._run_search)

        # Connections.
        self._input.textChanged.connect(lambda _: self._debounce.start())
        self._list.itemClicked.connect(self._on_item_clicked)
        self._list.itemDoubleClicked.connect(self._on_item_clicked)
        self._input.installEventFilter(self)

        # Watch parent resize events so the overlay stays full-coverage.
        if parent is not None:
            parent.installEventFilter(self)

    # -- Provider registration ------------------------------------------------

    def set_providers(self, providers: list[Any]) -> None:
        """Set the list of ``PaletteProvider`` instances."""
        self._providers = providers

    # -- Show / hide ----------------------------------------------------------

    def show_palette(self, initial_query: str = "") -> None:
        """Fill parent and show the overlay.

        Args:
            initial_query: Pre-populate the search field with this text.  Pass a
                non-empty string when launching from the topbar inline search so
                the user's partial input is forwarded into the palette.
        """
        self._list.clear()
        self._fill_to_parent()
        self.raise_()
        self.show()
        if initial_query:
            self._input.setText(initial_query)
            # Move cursor to end of pre-populated text.
            self._input.end(False)
        else:
            self._input.clear()
        self._run_search()  # Show results immediately.
        # Defer focus to after the triggering event (mouse-release / shortcut)
        # has fully unwound, so the source widget cannot reclaim focus after us.
        QTimer.singleShot(0, lambda: self._input.setFocus(Qt.FocusReason.OtherFocusReason))

    # -- Geometry helpers -----------------------------------------------------

    def _fill_to_parent(self) -> None:
        """Resize overlay to cover its parent widget completely."""
        p = self.parent()
        if isinstance(p, QWidget):
            self.setGeometry(0, 0, p.width(), p.height())
        self._position_panel()

    def _position_panel(self) -> None:
        """Centre the panel horizontally near the top of the overlay."""
        overlay_w = self.width()
        x = (overlay_w - self._PANEL_WIDTH) // 2
        y = self._PANEL_TOP_OFFSET
        self._panel.move(x, y)

    # -- Paint dim backdrop ---------------------------------------------------

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 80))
        painter.end()

    # -- Dismiss on outside click ---------------------------------------------

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if not self._panel.geometry().contains(event.position().toPoint()):
            self.hide()
            event.accept()
            return
        super().mousePressEvent(event)

    # -- Search ---------------------------------------------------------------

    def _run_search(self) -> None:
        query = self._input.text().strip()
        self._list.clear()

        all_results: list[PaletteResult] = []
        for provider in self._providers:
            try:
                results = provider.search(query)
                all_results.extend(results)
            except Exception:
                pass  # Never let a provider crash the palette.

        # Sort by score descending.
        all_results.sort(key=lambda r: r.score, reverse=True)

        # Group by category, preserving score order within each group.
        from collections import OrderedDict

        grouped: OrderedDict[str, list[PaletteResult]] = OrderedDict()
        for r in all_results:
            grouped.setdefault(r.category, []).append(r)

        # Populate list widget.
        for category, results in grouped.items():
            # Category header.
            header_item = QListWidgetItem(category)
            header_item.setData(_ROLE_IS_HEADER, True)
            header_item.setFlags(Qt.ItemFlag.NoItemFlags)  # Non-selectable.
            self._list.addItem(header_item)

            for result in results:
                item = QListWidgetItem(result.title)
                item.setData(_ROLE_RESULT, result)
                item.setData(_ROLE_IS_HEADER, False)
                self._list.addItem(item)

        # Pre-select first selectable row.
        self._select_first_result()
        self._adjust_height()

    def _select_first_result(self) -> None:
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item and not item.data(_ROLE_IS_HEADER):
                self._list.setCurrentItem(item)
                return

    def _adjust_height(self) -> None:
        """Size the panel to fit content, up to _PANEL_MAX_HEIGHT."""
        row_count = self._list.count()
        if row_count == 0:
            self._panel.setFixedHeight(self._INPUT_HEIGHT + 1 + 28)
            return

        total_h = 0
        for i in range(row_count):
            total_h += self._list.sizeHintForRow(i)
        content_h = self._INPUT_HEIGHT + 1 + total_h + 28 + 8
        self._panel.setFixedHeight(min(content_h, self._PANEL_MAX_HEIGHT))

    # -- Keyboard / event handling --------------------------------------------

    def eventFilter(self, obj, event: QEvent) -> bool:
        # Keep overlay full-coverage when the parent is resized.
        if obj is self.parent() and event.type() == QEvent.Type.Resize:
            if self.isVisible():
                self._fill_to_parent()
            return False  # Don't consume the event.

        # Key handling for the search input.
        if obj is self._input and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Escape:
                self.hide()
                return True
            if key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
                self._activate_current()
                return True
            if key == Qt.Key.Key_Down:
                self._move_selection(1)
                return True
            if key == Qt.Key.Key_Up:
                self._move_selection(-1)
                return True

        return super().eventFilter(obj, event)

    def _move_selection(self, direction: int) -> None:
        current = self._list.currentRow()
        count = self._list.count()
        if count == 0:
            return

        next_row = current + direction
        # Skip header rows.
        while 0 <= next_row < count:
            item = self._list.item(next_row)
            if item and not item.data(_ROLE_IS_HEADER):
                self._list.setCurrentRow(next_row)
                return
            next_row += direction

    def _activate_current(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        result: PaletteResult | None = item.data(_ROLE_RESULT)
        if result is None:
            return
        self.hide()
        try:
            result.action()
        except Exception:
            pass
        self.result_activated.emit()

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        if item.data(_ROLE_IS_HEADER):
            return
        result: PaletteResult | None = item.data(_ROLE_RESULT)
        if result is None:
            return
        self.hide()
        try:
            result.action()
        except Exception:
            pass
        self.result_activated.emit()
