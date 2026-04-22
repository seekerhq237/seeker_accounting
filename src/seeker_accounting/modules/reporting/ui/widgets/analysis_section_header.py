from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class AnalysisSectionHeader(QWidget):
    """Compact title block for 14H sections."""

    def __init__(
        self,
        title: str,
        subtitle: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        title_label = QLabel(title, self)
        title_label.setObjectName("AnalysisSectionTitle")
        layout.addWidget(title_label)

        if subtitle:
            subtitle_label = QLabel(subtitle, self)
            subtitle_label.setObjectName("AnalysisSectionSubtitle")
            subtitle_label.setWordWrap(True)
            layout.addWidget(subtitle_label)
