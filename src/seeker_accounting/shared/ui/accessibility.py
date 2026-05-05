"""Small accessibility helpers for Qt widgets."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractButton, QAbstractItemView, QWidget


def set_accessible_metadata(
    widget: QWidget,
    name: str,
    description: str | None = None,
) -> QWidget:
    widget.setAccessibleName(name)
    if description:
        widget.setAccessibleDescription(description)
    return widget


def mark_keyboard_focusable(widget: QWidget) -> QWidget:
    widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    widget.setProperty("keyboardFocusable", True)
    return widget


def describe_button(button: QAbstractButton, name: str, description: str | None = None) -> QAbstractButton:
    set_accessible_metadata(button, name, description)
    mark_keyboard_focusable(button)
    return button


def describe_item_view(
    view: QAbstractItemView,
    name: str,
    description: str | None = None,
) -> QAbstractItemView:
    set_accessible_metadata(view, name, description)
    mark_keyboard_focusable(view)
    return view