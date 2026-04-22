from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.reporting.dto.template_preview_dto import TemplatePreviewDTO


class ReportTemplatePreviewDialog(QDialog):
    """
    Template-preview dialog framework.

    Displays template metadata and a placeholder preview canvas.
    Real template rendering will be wired in the report engine slice.
    """

    def __init__(self, meta: TemplatePreviewDTO, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Template Preview — {meta.template_title}")
        self.setMinimumSize(700, 520)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(14)

        # ── header card ─────────────────────────────────────────────────
        header = QFrame(self)
        header.setObjectName("PageCard")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(20, 16, 20, 16)
        header_layout.setSpacing(8)

        title_lbl = QLabel(meta.template_title, header)
        title_lbl.setObjectName("InfoCardTitle")
        header_layout.addWidget(title_lbl)

        badge = QLabel(meta.standard_note, header)
        badge.setProperty("chipTone", "info")
        badge.setFixedWidth(
            badge.fontMetrics().horizontalAdvance(meta.standard_note) + 24
        )
        header_layout.addWidget(badge)

        desc_lbl = QLabel(meta.description, header)
        desc_lbl.setObjectName("PageSummary")
        desc_lbl.setWordWrap(True)
        header_layout.addWidget(desc_lbl)

        layout.addWidget(header)

        # ── template canvas placeholder ──────────────────────────────────
        canvas = QFrame(self)
        canvas.setObjectName("ReportCanvasPlaceholder")

        canvas_layout = QVBoxLayout(canvas)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        canvas_layout.setSpacing(6)

        canvas_lbl = QLabel("Template preview canvas", canvas)
        canvas_lbl.setObjectName("InfoCardTitle")
        canvas_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        canvas_layout.addWidget(canvas_lbl)

        canvas_sub = QLabel(
            "Statement template rendering will be implemented in the report engine slice.",
            canvas,
        )
        canvas_sub.setObjectName("PageSummary")
        canvas_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        canvas_layout.addWidget(canvas_sub)

        layout.addWidget(canvas, 1)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    @classmethod
    def show_template_preview(
        cls,
        meta: TemplatePreviewDTO,
        parent: QWidget | None = None,
    ) -> None:
        dialog = cls(meta, parent)
        dialog.exec()
