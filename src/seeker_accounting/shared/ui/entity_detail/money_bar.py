"""MoneyBar — horizontal KPI strip for entity detail workspaces.

Each MoneyBarItem shows a label, a formatted value, and an optional tone
(danger / warning / success / neutral) rendered as a coloured accent bar
at the top of the card.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

Tone = Literal["danger", "warning", "success", "info", "neutral"]


@dataclass
class MoneyBarItem:
    label: str
    value: str
    tone: Tone = "neutral"
    nav_id_on_click: str | None = None


# Tone → object-name suffix used in QSS
_TONE_SUFFIX: dict[str, str] = {
    "danger": "Danger",
    "warning": "Warning",
    "success": "Success",
    "info": "Info",
    "neutral": "Neutral",
}


class _MoneyCard(QFrame):
    """Single KPI card inside the MoneyBar."""

    clicked = Signal()

    def __init__(self, item: MoneyBarItem, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._item = item

        suffix = _TONE_SUFFIX.get(item.tone, "Neutral")
        self.setObjectName(f"MoneyCard{suffix}")
        self.setCursor(Qt.CursorShape.PointingHandCursor if item.nav_id_on_click else Qt.CursorShape.ArrowCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        self._value_label = QLabel(item.value, self)
        self._value_label.setObjectName("MoneyCardValue")
        self._value_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self._label_label = QLabel(item.label, self)
        self._label_label.setObjectName("MoneyCardLabel")
        self._label_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        layout.addWidget(self._value_label)
        layout.addWidget(self._label_label)

    def update_item(self, item: MoneyBarItem) -> None:
        self._item = item
        self._value_label.setText(item.value)
        self._label_label.setText(item.label)

    def mousePressEvent(self, event: object) -> None:
        if self._item.nav_id_on_click:
            self.clicked.emit()
        super().mousePressEvent(event)  # type: ignore[arg-type]


class MoneyBar(QFrame):
    """Horizontal strip of KPI cards for entity detail pages.

    Usage::

        bar = MoneyBar(parent=self)
        bar.set_items([
            MoneyBarItem("Overdue", "XAF 45,000", tone="danger"),
            MoneyBarItem("Open Balance", "XAF 125,000", tone="warning"),
            MoneyBarItem("Paid (30d)", "XAF 80,000", tone="success"),
        ])
    """

    item_clicked = Signal(str)   # emits nav_id_on_click

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("MoneyBar")
        self._cards: list[_MoneyCard] = []

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)

    def set_items(self, items: list[MoneyBarItem]) -> None:
        """Replace all cards with a new item list."""
        # Remove old cards
        for card in self._cards:
            self._layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()

        for item in items:
            card = _MoneyCard(item, self)
            if item.nav_id_on_click:
                nav_id = item.nav_id_on_click
                card.clicked.connect(lambda nid=nav_id: self.item_clicked.emit(nid))
            self._layout.addWidget(card)
            self._cards.append(card)

    def update_values(self, values: list[str]) -> None:
        """Fast-path: update only the value strings (label/tone unchanged)."""
        for card, value in zip(self._cards, values):
            card._value_label.setText(value)
