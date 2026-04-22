from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget


def create_field_block(label_text: str, field: QWidget, hint_text: str | None = None) -> QWidget:
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)

    label = QLabel(label_text, container)
    label.setProperty("role", "label")
    label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
    layout.addWidget(label)
    layout.addWidget(field)

    if hint_text:
        hint = QLabel(hint_text, container)
        hint.setWordWrap(True)
        hint.setProperty("role", "caption")
        layout.addWidget(hint)

    return container


def create_label_value_row(label_text: str, value_text: str, parent: QWidget | None = None) -> QWidget:
    container = QWidget(parent)
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)

    label = QLabel(label_text, container)
    label.setProperty("role", "caption")
    layout.addWidget(label)

    value = QLabel(value_text, container)
    value.setProperty("role", "value")
    value.setObjectName("ValueLabel")
    layout.addWidget(value, 1)
    return container

