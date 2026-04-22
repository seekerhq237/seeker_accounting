from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QWidget

from seeker_accounting.modules.reporting.dto.print_preview_dto import PrintPreviewMetaDTO
from seeker_accounting.modules.reporting.ui.dialogs.report_print_preview_dialog import (
    ReportPrintPreviewDialog,
)


class ReportChartPrintPreviewDialog(ReportPrintPreviewDialog):
    """Shared chart-aware print preview that reuses the reporting preview shell."""

    def __init__(
        self,
        meta: PrintPreviewMetaDTO,
        chart_snapshot: QPixmap | None = None,
        parent: QWidget | None = None,
    ) -> None:
        self._chart_snapshot = chart_snapshot
        super().__init__(meta, parent)

    def _build_header(self, meta: PrintPreviewMetaDTO) -> QWidget:
        header = super()._build_header(meta)
        if self._chart_snapshot is None or self._chart_snapshot.isNull():
            return header

        layout = header.layout()
        if layout is None:
            return header

        preview = QLabel(header)
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview.setPixmap(
            self._chart_snapshot.scaled(
                760,
                260,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        layout.addWidget(preview)
        return header

    @classmethod
    def show_preview(
        cls,
        meta: PrintPreviewMetaDTO,
        chart_snapshot: QPixmap | None = None,
        parent: QWidget | None = None,
    ) -> None:
        dialog = cls(meta, chart_snapshot=chart_snapshot, parent=parent)
        dialog.exec()
