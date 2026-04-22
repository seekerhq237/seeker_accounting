from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.reporting.dto.reporting_workspace_dto import ReportTileDTO


class ReportingTileCard(QFrame):
    """
    Polished launch tile card for reporting launcher tabs.
    Displays title, standard badge, description, status chip, and launch action.
    """

    launched = Signal(str)  # tile_key

    def __init__(self, tile_dto: ReportTileDTO, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tile_key = tile_dto.tile_key
        self.setObjectName("ReportTileCard")
        self.setMinimumHeight(240)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(10)

        title = QLabel(tile_dto.title, self)
        title.setObjectName("ReportTileTitle")
        layout.addWidget(title)

        if tile_dto.subtitle:
            badge = QLabel(tile_dto.subtitle, self)
            badge.setProperty("chipTone", "info")
            badge.setFixedWidth(badge.fontMetrics().horizontalAdvance(tile_dto.subtitle) + 24)
            layout.addWidget(badge)

        layout.addSpacing(4)

        desc = QLabel(tile_dto.description, self)
        desc.setObjectName("ReportTileDesc")
        desc.setWordWrap(True)
        layout.addWidget(desc, 1)

        layout.addSpacing(6)

        footer = QWidget(self)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(10)

        status_chip = QLabel("Framework Ready", footer)
        status_chip.setProperty("chipTone", "neutral")
        footer_layout.addWidget(status_chip)
        footer_layout.addStretch(1)

        launch_btn = QPushButton("Launch", footer)
        launch_btn.setProperty("variant", "primary")
        launch_btn.setFixedWidth(96)
        launch_btn.clicked.connect(lambda: self.launched.emit(self._tile_key))
        footer_layout.addWidget(launch_btn)

        layout.addWidget(footer)
