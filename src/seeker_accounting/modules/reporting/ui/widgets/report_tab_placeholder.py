from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from seeker_accounting.modules.reporting.dto.reporting_workspace_dto import ReportTabDTO


class ReportTabPlaceholder(QWidget):
    """
    Polished placeholder panel for report tabs not yet implemented.
    Shows a clean canvas shell prepared for future report engine integration.
    """

    def __init__(self, tab_dto: ReportTabDTO, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Section header
        title = QLabel(tab_dto.label, self)
        title.setObjectName("ReportTabSectionTitle")
        layout.addWidget(title)

        layout.addSpacing(6)

        desc = QLabel(tab_dto.description, self)
        desc.setObjectName("ReportTabSubtitle")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        layout.addSpacing(20)

        # Canvas placeholder
        canvas = QFrame(self)
        canvas.setObjectName("ReportCanvasPlaceholder")
        canvas.setMinimumHeight(280)

        canvas_layout = QVBoxLayout(canvas)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        canvas_layout.setSpacing(6)

        canvas_title = QLabel("Report canvas", canvas)
        canvas_title.setObjectName("CanvasPlaceholderTitle")
        canvas_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        canvas_layout.addWidget(canvas_title)

        canvas_sub = QLabel(
            "Report engine available in next implementation slice",
            canvas,
        )
        canvas_sub.setObjectName("CanvasPlaceholderSub")
        canvas_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        canvas_layout.addWidget(canvas_sub)

        layout.addWidget(canvas, 1)
