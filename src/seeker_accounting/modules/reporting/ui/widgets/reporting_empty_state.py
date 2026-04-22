from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class ReportingEmptyState(QWidget):
    """
    Reusable empty-state widget for report canvas areas.
    Shown when no report data is available or no company is selected.
    """

    def __init__(
        self,
        title: str = "No data available",
        message: str = "Select a company and reporting period, then click Refresh.",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)

        title_lbl = QLabel(title, self)
        title_lbl.setObjectName("InfoCardTitle")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_lbl)

        msg_lbl = QLabel(message, self)
        msg_lbl.setObjectName("PageSummary")
        msg_lbl.setWordWrap(True)
        msg_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(msg_lbl)
