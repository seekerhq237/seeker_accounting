from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.fixed_assets.dto.depreciation_dto import (
    DepreciationScheduleDTO,
    DepreciationScheduleLineDTO,
)
from seeker_accounting.shared.ui.message_boxes import show_error
from seeker_accounting.shared.ui.table_helpers import configure_compact_table

_METHOD_LABELS = {
    "straight_line": "Straight Line",
    "declining_balance": "Declining Balance",
    "double_declining_balance": "Double Declining Balance",
    "declining_balance_150": "150% Declining Balance",
    "reducing_balance": "Reducing Balance (DDB)",
    "sum_of_years_digits": "Sum of Years Digits",
    "units_of_production": "Units of Production",
    "component": "Component",
    "group": "Group",
    "composite": "Composite",
    "depletion": "Depletion",
    "annuity": "Annuity",
    "sinking_fund": "Sinking Fund",
    "macrs": "MACRS (GDS)",
    "amortization": "Amortization",
}


def _fmt(value) -> str:
    """Format a numeric amount: no decimals when value is whole, 2 decimals otherwise."""
    f = float(value)
    rounded = round(f, 2)
    if rounded == round(rounded):
        return f"{int(round(rounded)):,}"
    return f"{rounded:,.2f}"


class DepreciationSchedulePreviewDialog(QDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        asset_id: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._company_id = company_id
        self._asset_id = asset_id
        self._schedule: DepreciationScheduleDTO | None = None
        self._yearly_mode: bool = False

        self.setWindowTitle("Depreciation Schedule Preview")
        self.setModal(True)
        self.resize(860, 620)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # ── Summary card ──────────────────────────────────────────────
        self._summary_card = QFrame(self)
        self._summary_card.setObjectName("PageCard")
        summary_layout = QVBoxLayout(self._summary_card)
        summary_layout.setContentsMargins(8, 4, 8, 4)
        summary_layout.setSpacing(6)

        hdr = QLabel("Asset Summary", self._summary_card)
        hdr.setObjectName("CardTitle")
        summary_layout.addWidget(hdr)

        summary_grid = QWidget(self._summary_card)
        grid_layout = QHBoxLayout(summary_grid)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setSpacing(32)

        self._lbl_asset = self._make_kv_widget("Asset", "—")
        self._lbl_method = self._make_kv_widget("Method", "—")
        self._lbl_cost = self._make_kv_widget("Acquisition Cost", "—")
        self._lbl_salvage = self._make_kv_widget("Salvage Value", "—")
        self._lbl_base = self._make_kv_widget("Depreciable Base", "—")
        self._lbl_life = self._make_kv_widget("Useful Life", "—")

        for w in (self._lbl_asset, self._lbl_method, self._lbl_cost,
                  self._lbl_salvage, self._lbl_base, self._lbl_life):
            grid_layout.addWidget(w)
        grid_layout.addStretch(1)
        summary_layout.addWidget(summary_grid)
        layout.addWidget(self._summary_card)

        # ── Schedule table card ───────────────────────────────────────
        table_card = QFrame(self)
        table_card.setObjectName("PageCard")
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(8, 6, 8, 6)
        table_layout.setSpacing(10)

        # Toolbar row
        toolbar = QWidget(table_card)
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(0, 0, 0, 0)
        tb_layout.setSpacing(6)

        self._tbl_title = QLabel("Monthly Schedule", toolbar)
        self._tbl_title.setObjectName("CardTitle")
        tb_layout.addWidget(self._tbl_title)
        tb_layout.addSpacing(16)

        # Month / Year segmented toggle
        self._btn_monthly = QToolButton(toolbar)
        self._btn_monthly.setText("Monthly")
        self._btn_monthly.setCheckable(True)
        self._btn_monthly.setChecked(True)
        self._btn_monthly.setObjectName("SegLeft")

        self._btn_yearly = QToolButton(toolbar)
        self._btn_yearly.setText("Yearly")
        self._btn_yearly.setCheckable(True)
        self._btn_yearly.setObjectName("SegRight")

        view_group = QButtonGroup(toolbar)
        view_group.setExclusive(True)
        view_group.addButton(self._btn_monthly, 0)
        view_group.addButton(self._btn_yearly, 1)
        view_group.idToggled.connect(self._on_view_toggled)

        tb_layout.addWidget(self._btn_monthly)
        tb_layout.addWidget(self._btn_yearly)
        tb_layout.addStretch(1)

        self._total_label = QLabel(toolbar)
        self._total_label.setObjectName("ToolbarMeta")
        tb_layout.addWidget(self._total_label)

        tb_layout.addSpacing(12)

        self._btn_print = QPushButton("Print", toolbar)
        self._btn_print.setFixedWidth(72)
        self._btn_print.setEnabled(False)
        self._btn_print.clicked.connect(self._print_schedule)
        tb_layout.addWidget(self._btn_print)

        self._btn_pdf = QPushButton("Save PDF", toolbar)
        self._btn_pdf.setFixedWidth(80)
        self._btn_pdf.setEnabled(False)
        self._btn_pdf.clicked.connect(self._save_as_pdf)
        tb_layout.addWidget(self._btn_pdf)

        table_layout.addWidget(toolbar)

        self._table = QTableWidget(table_card)
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels((
            "Period", "Opening NBV", "Depreciation", "Accum. Depreciation", "Closing NBV",
        ))
        configure_compact_table(self._table)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table_layout.addWidget(self._table)
        layout.addWidget(table_card, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._load()

        from seeker_accounting.shared.ui.help_button import install_help_button
        install_help_button(self, "dialog.depreciation_schedule_preview")

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load(self) -> None:
        try:
            schedule = self._service_registry.depreciation_schedule_service.generate_schedule_for_asset(
                self._company_id, self._asset_id
            )
        except Exception as exc:
            show_error(self, "Depreciation Schedule", str(exc))
            return
        self._schedule = schedule
        self._populate_summary(schedule)
        self._refresh_table()
        self._btn_print.setEnabled(True)
        self._btn_pdf.setEnabled(True)

    def _populate_summary(self, s: DepreciationScheduleDTO) -> None:
        self._set_kv(self._lbl_asset, f"{s.asset_number} — {s.asset_name}")
        self._set_kv(self._lbl_method, _METHOD_LABELS.get(s.depreciation_method_code, s.depreciation_method_code))
        self._set_kv(self._lbl_cost, _fmt(s.acquisition_cost))
        self._set_kv(self._lbl_salvage, _fmt(s.salvage_value))
        self._set_kv(self._lbl_base, _fmt(s.depreciable_base))
        months = s.useful_life_months
        years, extra = divmod(months, 12)
        if years > 0 and extra > 0:
            life_str = f"{years} yr {extra} mo"
        elif years > 0:
            life_str = f"{years} yr"
        else:
            life_str = f"{months} mo"
        self._set_kv(self._lbl_life, life_str)
        self._total_label.setText(f"Total: {_fmt(s.total_depreciation)}")

    # ------------------------------------------------------------------
    # Table rendering
    # ------------------------------------------------------------------

    def _on_view_toggled(self, btn_id: int, checked: bool) -> None:
        if not checked:
            return
        self._yearly_mode = (btn_id == 1)
        self._tbl_title.setText("Yearly Schedule" if self._yearly_mode else "Monthly Schedule")
        self._refresh_table()

    def _refresh_table(self) -> None:
        if self._schedule is None:
            return
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)

        if self._yearly_mode:
            rows = self._aggregate_yearly(self._schedule.lines)
            for label, opening, charge, accum, closing in rows:
                self._insert_row(label, opening, charge, accum, closing)
        else:
            for line in self._schedule.lines:
                self._insert_row(
                    line.period_label,
                    line.opening_nbv,
                    line.depreciation_amount,
                    line.accumulated_depreciation,
                    line.closing_nbv,
                )

        self._table.resizeColumnsToContents()
        hdr = self._table.horizontalHeader()
        for col in range(1, 5):
            hdr.setSectionResizeMode(col, hdr.ResizeMode.Stretch)

    def _insert_row(self, label: str, opening, charge, accum, closing) -> None:
        ri = self._table.rowCount()
        self._table.insertRow(ri)
        self._table.setItem(ri, 0, QTableWidgetItem(label))
        for col, val in enumerate((opening, charge, accum, closing), start=1):
            item = QTableWidgetItem(_fmt(val))
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(ri, col, item)

    @staticmethod
    def _aggregate_yearly(
        lines: tuple[DepreciationScheduleLineDTO, ...],
    ) -> list[tuple[str, Decimal, Decimal, Decimal, Decimal]]:
        """Aggregate monthly lines into yearly rows."""
        if not lines:
            return []
        result = []
        i = 0
        year = 1
        while i < len(lines):
            chunk = lines[i: i + 12]
            opening = chunk[0].opening_nbv
            charge = sum((l.depreciation_amount for l in chunk), Decimal("0"))
            accum = chunk[-1].accumulated_depreciation
            closing = chunk[-1].closing_nbv
            result.append((f"Year {year}", opening, charge, accum, closing))
            i += 12
            year += 1
        return result

    # ------------------------------------------------------------------
    # Print / PDF
    # ------------------------------------------------------------------

    def _build_html(self) -> str:
        if self._schedule is None:
            return ""
        s = self._schedule
        method_label = _METHOD_LABELS.get(s.depreciation_method_code, s.depreciation_method_code)

        months = s.useful_life_months
        yrs, extra = divmod(months, 12)
        if yrs > 0 and extra > 0:
            life_str = f"{yrs} yr {extra} mo"
        elif yrs > 0:
            life_str = f"{yrs} yr"
        else:
            life_str = f"{months} mo"

        view_label = "Yearly" if self._yearly_mode else "Monthly"

        if self._yearly_mode:
            rows_data = [
                (label, opening, charge, accum, closing)
                for label, opening, charge, accum, closing
                in self._aggregate_yearly(s.lines)
            ]
        else:
            rows_data = [
                (l.period_label, l.opening_nbv, l.depreciation_amount,
                 l.accumulated_depreciation, l.closing_nbv)
                for l in s.lines
            ]

        row_html = "\n".join(
            f"""<tr class="{'even' if i % 2 == 0 else 'odd'}">
                <td>{label}</td>
                <td class="num">{_fmt(opening)}</td>
                <td class="num">{_fmt(charge)}</td>
                <td class="num">{_fmt(accum)}</td>
                <td class="num">{_fmt(closing)}</td>
            </tr>"""
            for i, (label, opening, charge, accum, closing) in enumerate(rows_data)
        )

        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>
  body {{ font-family: Arial, sans-serif; font-size: 10pt; color: #1a1a1a; margin: 20px; }}
  h2 {{ font-size: 13pt; margin: 0 0 4px 0; }}
  .subtitle {{ font-size: 9pt; color: #555; margin-bottom: 14px; }}
  .meta-grid {{ display: table; border-collapse: collapse; margin-bottom: 18px; width: 100%; }}
  .meta-cell {{ display: table-cell; padding: 6px 16px 6px 0; min-width: 100px; }}
  .meta-label {{ font-size: 8pt; color: #777; text-transform: uppercase; letter-spacing: 0.5px; }}
  .meta-value {{ font-size: 10pt; font-weight: bold; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 9pt; margin-top: 4px; }}
  th {{ background-color: #1e3a5f; color: #fff; padding: 7px 12px;
        font-size: 8.5pt; font-weight: 600; text-align: left; }}
  th.num {{ text-align: right; }}
  td {{ padding: 5px 12px; border-bottom: 1px solid #e8e8e8; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  tr.even {{ background: #ffffff; }}
  tr.odd {{ background: #f6f8fb; }}
  .footer {{ margin-top: 10px; font-size: 9pt; color: #444; text-align: right; font-weight: 600; }}
</style>
</head>
<body>
<h2>Depreciation Schedule &mdash; {s.asset_number}: {s.asset_name}</h2>
<div class="subtitle">{view_label} view &nbsp;&bull;&nbsp; Method: {method_label}</div>
<div class="meta-grid">
  <span class="meta-cell"><div class="meta-label">Acquisition Cost</div><div class="meta-value">{_fmt(s.acquisition_cost)}</div></span>
  <span class="meta-cell"><div class="meta-label">Salvage Value</div><div class="meta-value">{_fmt(s.salvage_value)}</div></span>
  <span class="meta-cell"><div class="meta-label">Depreciable Base</div><div class="meta-value">{_fmt(s.depreciable_base)}</div></span>
  <span class="meta-cell"><div class="meta-label">Useful Life</div><div class="meta-value">{life_str}</div></span>
</div>
<table>
  <tr>
    <th>Period</th>
    <th class="num">Opening NBV</th>
    <th class="num">Depreciation</th>
    <th class="num">Accum. Depreciation</th>
    <th class="num">Closing NBV</th>
  </tr>
  {row_html}
</table>
<div class="footer">Total depreciation: {_fmt(s.total_depreciation)}</div>
</body>
</html>"""

    def _print_schedule(self) -> None:
        try:
            from PySide6.QtGui import QTextDocument
            from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        except ImportError:
            show_error(self, "Print", "Printing is not available on this system.")
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setPageOrientation(printer.pageLayout().orientation().Landscape)
        dlg = QPrintDialog(printer, self)
        if dlg.exec() == QPrintDialog.DialogCode.Accepted:
            doc = QTextDocument()
            doc.setHtml(self._build_html())
            doc.print_(printer)

    def _save_as_pdf(self) -> None:
        try:
            from PySide6.QtGui import QTextDocument
            from PySide6.QtPrintSupport import QPrinter
        except ImportError:
            show_error(self, "Save PDF", "PDF export is not available on this system.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Depreciation Schedule as PDF", "", "PDF Files (*.pdf)"
        )
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(path)
        printer.setPageOrientation(printer.pageLayout().orientation().Landscape)
        doc = QTextDocument()
        doc.setHtml(self._build_html())
        doc.print_(printer)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_kv_widget(self, label: str, value: str) -> QWidget:
        container = QWidget(self)
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        lbl = QLabel(label, container)
        lbl.setProperty("role", "caption")
        v.addWidget(lbl)
        val = QLabel(value, container)
        val.setObjectName("ToolbarValue")
        val.setProperty("_val_label", True)
        v.addWidget(val)
        return container

    def _set_kv(self, widget: QWidget, value: str) -> None:
        for child in widget.findChildren(QLabel):
            if child.property("_val_label"):
                child.setText(value)
                return
