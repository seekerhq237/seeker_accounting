from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.reporting.dto.print_preview_dto import (
    PrintPreviewMetaDTO,
    PrintPreviewRowDTO,
)


class ReportPrintPreviewDialog(QDialog):
    """Print-preview dialog for reporting surfaces."""

    def __init__(self, meta: PrintPreviewMetaDTO, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._amount_headers = meta.amount_headers
        self.setWindowTitle(f"Print Preview - {meta.report_title}")
        self.setMinimumSize(820, 620)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(14)

        layout.addWidget(self._build_header(meta))
        if meta.rows:
            layout.addWidget(self._build_rows_table(meta.rows), 1)
        else:
            layout.addWidget(self._build_placeholder_canvas(), 1)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _build_header(self, meta: PrintPreviewMetaDTO) -> QWidget:
        header_card = QFrame(self)
        header_card.setObjectName("PageCard")
        header_layout = QVBoxLayout(header_card)
        header_layout.setContentsMargins(20, 16, 20, 16)
        header_layout.setSpacing(8)

        report_title_lbl = QLabel(meta.report_title, header_card)
        report_title_lbl.setObjectName("InfoCardTitle")
        header_layout.addWidget(report_title_lbl)

        if meta.template_title:
            template_badge = QLabel(meta.template_title, header_card)
            template_badge.setProperty("chipTone", "info")
            header_layout.addWidget(template_badge)

        meta_row = QWidget(header_card)
        meta_row_layout = QHBoxLayout(meta_row)
        meta_row_layout.setContentsMargins(0, 0, 0, 0)
        meta_row_layout.setSpacing(24)

        self._add_pair(meta_row_layout, "Company:", meta.company_name or "-")
        self._add_pair(meta_row_layout, "Period:", meta.period_label)
        self._add_pair(meta_row_layout, "Generated:", meta.generated_at)
        self._add_pair(meta_row_layout, "Filter:", meta.filter_summary)
        meta_row_layout.addStretch(1)
        header_layout.addWidget(meta_row)
        return header_card

    def _build_rows_table(self, rows: tuple[PrintPreviewRowDTO, ...]) -> QWidget:
        table = QTableWidget(self)
        amount_headers = self._resolve_amount_headers(rows)
        headers = ["Ref", "Line", *amount_headers]
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(rows))
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(28)
        table.setWordWrap(False)
        table.setAlternatingRowColors(False)
        table.setShowGrid(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.horizontalHeader().setStretchLastSection(False)
        table.setColumnWidth(0, 90)
        table.setColumnWidth(1, 470)
        for column in range(2, len(headers)):
            table.setColumnWidth(column, 160)

        for row_index, row in enumerate(rows):
            self._bind_row(table, row_index, row, len(amount_headers))

        return table

    def _build_placeholder_canvas(self) -> QWidget:
        canvas = QFrame(self)
        canvas.setObjectName("PrintCanvasFrame")

        canvas_layout = QVBoxLayout(canvas)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        canvas_layout.setSpacing(6)

        canvas_lbl = QLabel("Print canvas", canvas)
        canvas_lbl.setObjectName("InfoCardTitle")
        canvas_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        canvas_layout.addWidget(canvas_lbl)

        canvas_sub = QLabel(
            "Report rendering will appear here when the report supplies preview rows.",
            canvas,
        )
        canvas_sub.setObjectName("PageSummary")
        canvas_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        canvas_layout.addWidget(canvas_sub)
        return canvas

    def _bind_row(
        self,
        table: QTableWidget,
        row_index: int,
        row: PrintPreviewRowDTO,
        amount_column_count: int,
    ) -> None:
        ref_item = QTableWidgetItem(row.reference_code or "")
        label_item = QTableWidgetItem(row.label)
        amount_items = [
            QTableWidgetItem(row.amount_text or ""),
            QTableWidgetItem(row.secondary_amount_text or ""),
            QTableWidgetItem(row.tertiary_amount_text or ""),
            QTableWidgetItem(row.quaternary_amount_text or ""),
        ][:amount_column_count]
        for amount_item in amount_items:
            amount_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        if row.row_type == "section":
            font = label_item.font()
            font.setBold(True)
            font.setPointSize(font.pointSize() + 1)
            ref_item.setFont(font)
            label_item.setFont(font)
            for amount_item in amount_items:
                amount_item.setFont(font)
        elif row.row_type == "subtotal":
            font = label_item.font()
            font.setBold(True)
            ref_item.setFont(font)
            label_item.setFont(font)
            for amount_item in amount_items:
                amount_item.setFont(font)

        table.setItem(row_index, 0, ref_item)
        table.setItem(row_index, 1, label_item)
        for offset, amount_item in enumerate(amount_items, start=2):
            table.setItem(row_index, offset, amount_item)

    def _resolve_amount_headers(self, rows: tuple[PrintPreviewRowDTO, ...]) -> tuple[str, ...]:
        has_secondary = any((row.secondary_amount_text or "").strip() for row in rows)
        has_tertiary = any((row.tertiary_amount_text or "").strip() for row in rows)
        has_quaternary = any((row.quaternary_amount_text or "").strip() for row in rows)
        headers = list(getattr(self, "_amount_headers", ("Amount",)))
        if not headers:
            headers = ["Amount"]
        if has_quaternary:
            while len(headers) < 4:
                headers.append(f"Amount {len(headers) + 1}")
            return tuple(headers[:4])
        if has_tertiary:
            while len(headers) < 3:
                headers.append(f"Amount {len(headers) + 1}")
            return tuple(headers[:3])
        if has_secondary:
            while len(headers) < 2:
                headers.append(f"Amount {len(headers) + 1}")
            return tuple(headers[:2])
        return (headers[0],)

    def _add_pair(self, layout: QHBoxLayout, label: str, value: str) -> None:
        pair = QWidget(self)
        pair_layout = QHBoxLayout(pair)
        pair_layout.setContentsMargins(0, 0, 0, 0)
        pair_layout.setSpacing(6)
        lbl = QLabel(label, pair)
        lbl.setProperty("role", "caption")
        pair_layout.addWidget(lbl)
        val = QLabel(value, pair)
        val.setObjectName("TopBarValue")
        pair_layout.addWidget(val)
        layout.addWidget(pair)

    @classmethod
    def show_preview(
        cls,
        meta: PrintPreviewMetaDTO,
        parent: QWidget | None = None,
    ) -> None:
        dialog = cls(meta, parent)
        dialog.exec()
