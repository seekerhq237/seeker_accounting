"""Full-window overlay for contextual help — mirrors the CommandPalette visual pattern.

The ``HelpOverlay`` is a child of the shell root frame.  It paints a translucent
dim backdrop and shows a floating panel with the help article for the current
page or dialog.

Usage from a page / dialog:

    from seeker_accounting.shared.ui.help_overlay import show_help
    show_help("customers", parent_widget)
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.shared.ui.help_content import HELP_CONTENT


# ---------------------------------------------------------------------------
# HelpOverlay widget
# ---------------------------------------------------------------------------

class HelpOverlay(QWidget):
    """Full-window overlay that displays a contextual help article.

    Designed as a child of the shell root QFrame (same parent model as
    ``CommandPalette``).  Click-outside or Escape dismisses.
    """

    _PANEL_WIDTH = 560
    _PANEL_MAX_HEIGHT = 520
    _PANEL_TOP_OFFSET = 72  # a bit lower than the command palette

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("HelpOverlay")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.hide()

        # ── Floating panel ────────────────────────────────────────────────
        self._panel = QFrame(self)
        self._panel.setObjectName("HelpPanel")
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

        # Header bar (title + close button).
        header = QFrame(self._panel)
        header.setObjectName("HelpPanelHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 10, 10, 10)
        header_layout.setSpacing(8)

        self._title_label = QLabel("Help", header)
        self._title_label.setObjectName("HelpPanelTitle")
        header_layout.addWidget(self._title_label, 1)

        close_btn = QPushButton("✕", header)
        close_btn.setObjectName("HelpPanelClose")
        close_btn.setFixedSize(28, 28)
        close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close_btn.clicked.connect(self.hide)
        header_layout.addWidget(close_btn)
        panel_layout.addWidget(header)

        # Separator.
        sep = QFrame(self._panel)
        sep.setObjectName("HelpPanelSep")
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        panel_layout.addWidget(sep)

        # Scrollable body area.
        scroll = QScrollArea(self._panel)
        scroll.setObjectName("HelpPanelScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        body_container = QWidget(scroll)
        body_container.setObjectName("HelpPanelBodyContainer")
        body_layout = QVBoxLayout(body_container)
        body_layout.setContentsMargins(20, 14, 20, 14)
        body_layout.setSpacing(8)

        self._summary_label = QLabel(body_container)
        self._summary_label.setObjectName("HelpPanelSummary")
        self._summary_label.setWordWrap(True)
        body_layout.addWidget(self._summary_label)

        self._body_label = QLabel(body_container)
        self._body_label.setObjectName("HelpPanelBody")
        self._body_label.setWordWrap(True)
        self._body_label.setTextFormat(Qt.TextFormat.RichText)
        self._body_label.setOpenExternalLinks(False)
        body_layout.addWidget(self._body_label)
        body_layout.addStretch()

        scroll.setWidget(body_container)
        panel_layout.addWidget(scroll, 1)

        # Hint bar.
        hint_bar = QFrame(self._panel)
        hint_bar.setObjectName("HelpPanelHintBar")
        hint_layout = QHBoxLayout(hint_bar)
        hint_layout.setContentsMargins(14, 4, 14, 6)
        hint_hint = QLabel("Esc Close", hint_bar)
        hint_hint.setObjectName("HelpPanelHintLabel")
        hint_layout.addWidget(hint_hint)
        hint_layout.addStretch()
        panel_layout.addWidget(hint_bar)

        # Watch parent resize.
        if parent is not None:
            parent.installEventFilter(self)

    # -- Public API -----------------------------------------------------------

    def show_help(self, help_key: str) -> None:
        """Populate the overlay with the article for *help_key* and show it."""
        article = HELP_CONTENT.get(help_key)
        if article is None:
            self._title_label.setText("Help")
            self._summary_label.setText("No contextual help available for this view.")
            self._body_label.setText("")
        else:
            self._title_label.setText(article.title)
            self._summary_label.setText(article.summary)
            self._body_label.setText(article.body_html)

        self._fill_to_parent()
        self.raise_()
        self.show()
        self._panel.setFixedHeight(self._PANEL_MAX_HEIGHT)

    # -- Geometry helpers -----------------------------------------------------

    def _fill_to_parent(self) -> None:
        p = self.parent()
        if isinstance(p, QWidget):
            self.setGeometry(0, 0, p.width(), p.height())
        self._position_panel()

    def _position_panel(self) -> None:
        x = (self.width() - self._PANEL_WIDTH) // 2
        y = self._PANEL_TOP_OFFSET
        self._panel.move(x, y)

    # -- Dim backdrop paint ---------------------------------------------------

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

    # -- Event filter (parent resize + Escape) --------------------------------

    def eventFilter(self, obj, event: QEvent) -> bool:
        if obj is self.parent() and event.type() == QEvent.Type.Resize:
            if self.isVisible():
                self._fill_to_parent()
            return False
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            event.accept()
            return
        super().keyPressEvent(event)


# ---------------------------------------------------------------------------
# Module-level singleton + convenience function
# ---------------------------------------------------------------------------

_overlay_instance: HelpOverlay | None = None


def _is_alive(obj: QWidget) -> bool:
    """Return True if the underlying C++ object is still valid."""
    try:
        from shiboken6 import isValid  # type: ignore[import-untyped]
        return isValid(obj)
    except ImportError:
        try:
            obj.parent()
            return True
        except RuntimeError:
            return False


def _get_overlay(widget: QWidget) -> HelpOverlay:
    """Return the singleton ``HelpOverlay``, parented to the shell root."""
    global _overlay_instance
    if _overlay_instance is not None and _is_alive(_overlay_instance) and _overlay_instance.parent() is not None:
        return _overlay_instance

    # Walk up to the ShellRoot frame (same strategy as CommandPalette).
    shell_root = widget.window()
    if hasattr(shell_root, "centralWidget"):
        cw = shell_root.centralWidget()  # type: ignore[union-attr]
        if cw is not None:
            shell_root = cw
    _overlay_instance = HelpOverlay(parent=shell_root)
    return _overlay_instance


def show_help(help_key: str, source_widget: QWidget) -> None:
    """Show the global help overlay for *help_key*.

    Call from any widget — the overlay will parent itself to the shell root
    automatically.  For modal dialogs use :func:`show_help_in_dialog` instead
    so the overlay appears above the dialog.
    """
    overlay = _get_overlay(source_widget)
    overlay.show_help(help_key)


def show_help_in_dialog(help_key: str, dialog: QWidget) -> None:
    """Show contextual help in a standalone popup dialog.

    Used for modal dialogs where the shell-level overlay would appear
    behind.  A separate ``QDialog`` always renders above the caller
    regardless of the caller's size.
    """
    from PySide6.QtWidgets import QDialog

    article = HELP_CONTENT.get(help_key)

    dlg = QDialog(dialog)
    dlg.setWindowTitle("Help")
    dlg.setModal(True)
    dlg.resize(520, 460)
    dlg.setObjectName("HelpPopupDialog")

    # Reuse the same panel structure / object names so existing QSS applies.
    panel = QFrame(dlg)
    panel.setObjectName("HelpPanel")

    panel_layout = QVBoxLayout(panel)
    panel_layout.setContentsMargins(0, 0, 0, 0)
    panel_layout.setSpacing(0)

    # Header
    header = QFrame(panel)
    header.setObjectName("HelpPanelHeader")
    header_layout = QHBoxLayout(header)
    header_layout.setContentsMargins(16, 10, 10, 10)
    header_layout.setSpacing(8)

    title_label = QLabel(article.title if article else "Help", header)
    title_label.setObjectName("HelpPanelTitle")
    header_layout.addWidget(title_label, 1)

    close_btn = QPushButton("\u2715", header)
    close_btn.setObjectName("HelpPanelClose")
    close_btn.setFixedSize(28, 28)
    close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    close_btn.clicked.connect(dlg.close)
    header_layout.addWidget(close_btn)
    panel_layout.addWidget(header)

    # Separator
    sep = QFrame(panel)
    sep.setObjectName("HelpPanelSep")
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setFixedHeight(1)
    panel_layout.addWidget(sep)

    # Scrollable body
    scroll = QScrollArea(panel)
    scroll.setObjectName("HelpPanelScroll")
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    body_container = QWidget(scroll)
    body_container.setObjectName("HelpPanelBodyContainer")
    body_layout = QVBoxLayout(body_container)
    body_layout.setContentsMargins(20, 14, 20, 14)
    body_layout.setSpacing(8)

    summary_label = QLabel(body_container)
    summary_label.setObjectName("HelpPanelSummary")
    summary_label.setWordWrap(True)
    if article:
        summary_label.setText(article.summary)
    else:
        summary_label.setText("No contextual help available for this view.")
    body_layout.addWidget(summary_label)

    body_label = QLabel(body_container)
    body_label.setObjectName("HelpPanelBody")
    body_label.setWordWrap(True)
    body_label.setTextFormat(Qt.TextFormat.RichText)
    body_label.setOpenExternalLinks(False)
    if article:
        body_label.setText(article.body_html)
    body_layout.addWidget(body_label)
    body_layout.addStretch()

    scroll.setWidget(body_container)
    panel_layout.addWidget(scroll, 1)

    # Hint bar
    hint_bar = QFrame(panel)
    hint_bar.setObjectName("HelpPanelHintBar")
    hint_layout = QHBoxLayout(hint_bar)
    hint_layout.setContentsMargins(14, 4, 14, 6)
    hint_label = QLabel("Esc Close", hint_bar)
    hint_label.setObjectName("HelpPanelHintLabel")
    hint_layout.addWidget(hint_label)
    hint_layout.addStretch()
    panel_layout.addWidget(hint_bar)

    # Fill the dialog with the panel
    outer = QVBoxLayout(dlg)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.addWidget(panel)

    dlg.exec()
