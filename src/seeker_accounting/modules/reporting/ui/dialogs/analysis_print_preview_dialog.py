from __future__ import annotations

from PySide6.QtWidgets import QWidget

from seeker_accounting.modules.reporting.dto.print_preview_dto import PrintPreviewMetaDTO
from seeker_accounting.modules.reporting.ui.dialogs.report_print_preview_dialog import (
    ReportPrintPreviewDialog,
)


class AnalysisPrintPreviewDialog(ReportPrintPreviewDialog):
    """Slice 14H print-preview wrapper that reuses the shared reporting preview shell."""

    @classmethod
    def show_preview(
        cls,
        meta: PrintPreviewMetaDTO,
        parent: QWidget | None = None,
    ) -> None:
        dialog = cls(meta, parent)
        dialog.exec()
