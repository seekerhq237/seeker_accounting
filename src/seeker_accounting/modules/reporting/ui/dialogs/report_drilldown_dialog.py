from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.reporting.dto.drilldown_request_dto import DrilldownRequestDTO

_DRILL_TYPE_LABELS: dict[str, str] = {
    "account_ledger": "Account Ledger",
    "journal_detail": "Journal Detail",
    "report_line": "Report Line Detail",
}


class ReportDrilldownDialog(QDialog):
    """
    Reusable drilldown dialog framework for the reporting workspace.

    Supports account ledger, journal detail, and report-line detail paths.
    Real query logic will be wired in the GL and trial balance engine slices.
    """

    def __init__(
        self,
        request: DrilldownRequestDTO,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        drill_label = _DRILL_TYPE_LABELS.get(request.drill_type, request.drill_type.title())
        self.setWindowTitle(f"Drilldown — {request.display_label}")
        self.setMinimumSize(740, 520)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(14)

        # ── context header ───────────────────────────────────────────────
        header = QFrame(self)
        header.setObjectName("PageCard")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(20, 16, 20, 16)
        header_layout.setSpacing(8)

        ref_lbl = QLabel(request.display_label, header)
        ref_lbl.setObjectName("InfoCardTitle")
        header_layout.addWidget(ref_lbl)

        meta_row = QWidget(header)
        meta_row_layout = QHBoxLayout(meta_row)
        meta_row_layout.setContentsMargins(0, 0, 0, 0)
        meta_row_layout.setSpacing(24)

        def _add_pair(label: str, value: str) -> None:
            w = QWidget(meta_row)
            wl = QHBoxLayout(w)
            wl.setContentsMargins(0, 0, 0, 0)
            wl.setSpacing(6)
            lbl = QLabel(label, w)
            lbl.setProperty("role", "caption")
            wl.addWidget(lbl)
            val = QLabel(value, w)
            val.setObjectName("TopBarValue")
            wl.addWidget(val)
            meta_row_layout.addWidget(w)

        _add_pair("Source:", request.source_report or "—")
        _add_pair("Type:", drill_label)
        _add_pair("Ref:", request.reference_code or str(request.reference_id or "—"))

        if request.date_from or request.date_to:
            from_str = request.date_from.strftime("%d %b %Y") if request.date_from else "—"
            to_str = request.date_to.strftime("%d %b %Y") if request.date_to else "—"
            _add_pair("Period:", f"{from_str} – {to_str}")

        meta_row_layout.addStretch(1)
        header_layout.addWidget(meta_row)
        layout.addWidget(header)

        # ── detail canvas placeholder ────────────────────────────────────
        canvas = QFrame(self)
        canvas.setObjectName("DrilldownFrame")

        canvas_layout = QVBoxLayout(canvas)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        canvas_layout.setSpacing(6)

        canvas_lbl = QLabel("Drilldown detail canvas", canvas)
        canvas_lbl.setObjectName("InfoCardTitle")
        canvas_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        canvas_layout.addWidget(canvas_lbl)

        canvas_sub = QLabel(
            "GL and transaction detail queries will be wired in the report engine slice.",
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
    def show_drilldown(
        cls,
        request: DrilldownRequestDTO,
        parent: QWidget | None = None,
    ) -> None:
        dialog = cls(request, parent)
        dialog.exec()
