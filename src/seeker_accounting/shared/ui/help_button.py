"""Floating help button factory for page and dialog widgets.

Call ``install_help_button(page_widget, help_key)`` for page widgets
(bottom-right) or ``install_help_button(dialog, help_key, dialog=True)``
for QDialog subclasses (bottom-left, dialog-local overlay).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QPushButton, QWidget


def install_help_button(
    page: QWidget, help_key: str, *, dialog: bool = False,
) -> QPushButton:
    """Create and install a floating help button on *page*.

    If *dialog* is True the button is placed bottom-left and the overlay
    opens inside the dialog window (correct z-order for modal dialogs).
    Otherwise it is placed bottom-right and uses the shell-level overlay.
    """
    btn = QPushButton("?", page)
    btn.setObjectName("HelpButton")
    btn.setFixedSize(32, 32)
    btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    btn.setToolTip("Help")
    btn.raise_()

    is_dialog = dialog or isinstance(page, QDialog)

    def _on_clicked() -> None:
        if is_dialog:
            from seeker_accounting.shared.ui.help_overlay import show_help_in_dialog
            show_help_in_dialog(help_key, page)
        else:
            from seeker_accounting.shared.ui.help_overlay import show_help
            show_help(help_key, page)

    btn.clicked.connect(_on_clicked)

    def _pos_right() -> None:
        btn.move(page.width() - 48, page.height() - 48)

    def _pos_left() -> None:
        btn.move(16, page.height() - 48)

    _position = _pos_left if is_dialog else _pos_right

    # Monkey-patch resizeEvent to keep the button positioned.
    _original_resize = page.resizeEvent

    def _patched_resize(event) -> None:  # type: ignore[no-untyped-def]
        _original_resize(event)
        _position()

    page.resizeEvent = _patched_resize  # type: ignore[assignment]

    # Position immediately for the current size.
    _position()
    return btn
