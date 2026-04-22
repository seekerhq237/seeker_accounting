"""PDF renderer for financial statements using Chromium (QWebEnginePage).

Delegates to WebDocumentRenderer from platform.printing for pixel-perfect
PDF output.  The HTML building logic is unchanged; only the rendering
backend has moved from QPrinter+QTextDocument to Chromium.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from html import escape as _h
from typing import Sequence



from seeker_accounting.modules.reporting.export.export_models import (
    StatementCompanyInfo,
    StatementExportRow,
    StatementPageOrientation,
    StatementPageSize,
    StatementTableSection,
)

_BRAND_PRIMARY = "#1E3A5F"
_BRAND_LIGHT = "#F0F3F7"
_BRAND_BORDER = "#D0D7DE"
_SECTION_BG = "#EDF1F6"
_SUBTOTAL_BG = "#F5F6F8"
_TOTAL_BG = "#E6EAF0"
_HIGHLIGHT_BG = "#FFFCE8"
_ZERO = Decimal("0.00")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class FinancialStatementPdfRenderer:
    """Renders financial statements to PDF via HTML + Qt print pipeline.

    Accepts a list of ``StatementTableSection`` objects so that each
    financial statement can define its own column structure and visual
    layout independently.
    """

    def render(
        self,
        *,
        title: str,
        subtitle: str | None,
        date_label: str,
        company: StatementCompanyInfo,
        sections: Sequence[StatementTableSection],
        summary_pairs: Sequence[tuple[str, str]],
        output_path: str,
        page_size: StatementPageSize,
        orientation: StatementPageOrientation,
    ) -> None:
        html = self._build_html(
            title=title,
            subtitle=subtitle,
            date_label=date_label,
            company=company,
            sections=sections,
            summary_pairs=summary_pairs,
            page_size=page_size,
            orientation=orientation,
        )
        self._render_to_pdf(html, output_path, page_size, orientation)

    # ------------------------------------------------------------------
    # HTML assembly
    # ------------------------------------------------------------------

    def _build_html(
        self,
        *,
        title: str,
        subtitle: str | None,
        date_label: str,
        company: StatementCompanyInfo,
        sections: Sequence[StatementTableSection],
        summary_pairs: Sequence[tuple[str, str]],
        page_size: StatementPageSize,
        orientation: StatementPageOrientation | None = None,
    ) -> str:
        parts: list[str] = []
        parts.append(self._company_header_html(company))
        parts.append(self._title_block_html(title, subtitle, date_label))

        for section in sections:
            parts.append(self._section_html(section))

        if summary_pairs:
            parts.append(self._summary_html(summary_pairs))
        parts.append(self._footer_html())
        body = "\n".join(parts)
        return self._wrap_html(body, page_size, orientation)

    # ------------------------------------------------------------------
    # Company header
    # ------------------------------------------------------------------

    @staticmethod
    def _logo_inline_uri(logo_path: str) -> str | None:
        """Return a base64 data URI for the logo, or None on failure."""
        try:
            import base64
            from pathlib import Path
            p = Path(logo_path)
            if not p.exists():
                return None
            data = p.read_bytes()
            mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                    "webp": "image/webp"}.get(p.suffix.lower().lstrip("."), "image/png")
            return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
        except Exception:
            return None

    def _company_header_html(self, company: StatementCompanyInfo) -> str:
        lines: list[str] = []
        lines.append('<div class="co-header">')
        if company.logo_path:
            logo_src = self._logo_inline_uri(company.logo_path)
            if logo_src:
                lines.append(f'  <img class="co-logo" src="{logo_src}" />')
        lines.append(f'  <div class="co-name">{_h(company.name)}</div>')
        if company.legal_name and company.legal_name != company.name:
            lines.append(f'  <div class="co-legal">{_h(company.legal_name)}</div>')
        for addr in company.address_block:
            lines.append(f'  <div class="co-addr">{_h(addr)}</div>')
        id_parts: list[str] = []
        if company.tax_identifier:
            id_parts.append(f"Tax ID: {_h(company.tax_identifier)}")
        if company.registration_number:
            id_parts.append(f"Reg: {_h(company.registration_number)}")
        if id_parts:
            lines.append(f'  <div class="co-ids">{" &middot; ".join(id_parts)}</div>')
        lines.append("</div>")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Title block
    # ------------------------------------------------------------------

    def _title_block_html(self, title: str, subtitle: str | None, date_label: str) -> str:
        parts: list[str] = ['<div class="title-block">']
        parts.append(f'  <div class="report-title">{_h(title)}</div>')
        if subtitle:
            parts.append(f'  <div class="report-subtitle">{_h(subtitle)}</div>')
        parts.append(f'  <div class="report-date">{_h(date_label)}</div>')
        parts.append("</div>")
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Section (heading + table)
    # ------------------------------------------------------------------

    def _section_html(self, section: StatementTableSection) -> str:
        parts: list[str] = []
        if section.heading:
            parts.append(
                f'<div class="section-heading">{_h(section.heading)}</div>'
            )
        parts.append(self._table_html(section.column_headers, section.rows))
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Table
    # ------------------------------------------------------------------

    def _table_html(
        self,
        headers: Sequence[str],
        rows: Sequence[StatementExportRow],
    ) -> str:
        num_cols = len(headers)
        parts: list[str] = ['<table class="stmt-table">']
        # Column group for widths
        parts.append("  <colgroup>")
        parts.append('    <col class="col-ref" />')
        parts.append('    <col class="col-lbl" />')
        for _ in range(max(0, num_cols - 2)):
            parts.append('    <col class="col-amt" />')
        parts.append("  </colgroup>")
        # Header
        parts.append("  <thead><tr>")
        for i, hdr in enumerate(headers):
            cls = ' class="num"' if i >= 2 else ""
            parts.append(f"    <th{cls}>{_h(hdr)}</th>")
        parts.append("  </tr></thead>")
        # Body
        parts.append("  <tbody>")
        for row in rows:
            parts.append(self._row_html(row, num_cols))
        parts.append("  </tbody>")
        parts.append("</table>")
        return "\n".join(parts)

    def _row_html(self, row: StatementExportRow, col_count: int) -> str:
        kind = row.row_kind
        css_classes: list[str] = [f"rk-{kind}"]
        if row.is_highlight:
            css_classes.append("highlight")
        cls_attr = f' class="{" ".join(css_classes)}"'
        cells: list[str] = []

        # Ref cell — blank for section rows
        ref_text = row.ref_code if kind not in ("section",) else ""
        cells.append(f'    <td class="ref">{_h(ref_text)}</td>')

        # Label cell with indent
        indent_px = row.indent_level * 18
        style = f' style="padding-left:{indent_px + 8}px"' if indent_px > 0 else ""
        cells.append(f'    <td class="lbl"{style}>{_h(row.label)}</td>')

        # Amount cells
        amount_count = col_count - 2
        for i in range(amount_count):
            val = row.amounts[i] if i < len(row.amounts) else None
            cells.append(f'    <td class="num">{self._fmt_amount(val)}</td>')

        return f"  <tr{cls_attr}>\n" + "\n".join(cells) + "\n  </tr>"

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def _summary_html(self, pairs: Sequence[tuple[str, str]]) -> str:
        parts: list[str] = ['<table class="summary-table">']
        for idx, (label, value) in enumerate(pairs):
            is_last = idx == len(pairs) - 1
            cls = ' class="summary-last"' if is_last else ""
            parts.append(
                f"  <tr{cls}>"
                f'<td class="summary-label">{_h(label)}</td>'
                f'<td class="summary-value">{_h(value)}</td>'
                f"</tr>"
            )
        parts.append("</table>")
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Footer
    # ------------------------------------------------------------------

    def _footer_html(self) -> str:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        return (
            '<div class="footer">'
            f"Seeker Accounting &middot; Generated {_h(now)}"
            "</div>"
        )

    # ------------------------------------------------------------------
    # Wrap
    # ------------------------------------------------------------------

    def _wrap_html(self, body: str, page_size: StatementPageSize, orientation: StatementPageOrientation | None = None) -> str:
        font_pt = page_size.body_font_pt
        css = self._css(page_size, orientation)
        return (
            "<!DOCTYPE html>\n"
            "<html><head>\n"
            f"<style>{css}</style>\n"
            "</head>\n"
            f'<body style="font-size:{font_pt}pt">\n'
            f"{body}\n"
            "</body></html>"
        )

    # ------------------------------------------------------------------
    # CSS
    # ------------------------------------------------------------------

    def _css(self, page_size: StatementPageSize, orientation: StatementPageOrientation | None = None) -> str:
        fp = page_size.body_font_pt
        w_mm, h_mm = page_size.dimensions_mm
        margin = page_size.margin_mm
        # Chromium uses CSS @page for layout — pass margin_mm=0 to WebDocumentRenderer
        if orientation == StatementPageOrientation.LANDSCAPE:
            page_rule = f"@page {{ size: {h_mm}mm {w_mm}mm landscape; margin: {margin}mm; }}"
        else:
            page_rule = f"@page {{ size: {w_mm}mm {h_mm}mm portrait; margin: {margin}mm; }}"
        return f"""
        {page_rule}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
            font-size: {fp}pt;
            color: #1a1a1a;
            line-height: 1.35;
        }}

        /* --- Company header --- */
        .co-header {{ margin-bottom: 10px; }}
        .co-logo {{ max-height: 44px; max-width: 150px; margin-bottom: 4px; }}
        .co-name {{ font-size: {fp + 4}pt; font-weight: 700; color: {_BRAND_PRIMARY}; }}
        .co-legal {{ font-size: {fp}pt; color: #555; }}
        .co-addr {{ font-size: {fp - 1}pt; color: #666; }}
        .co-ids {{ font-size: {fp - 1}pt; color: #666; margin-top: 2px; }}

        /* --- Title block --- */
        .title-block {{
            margin: 10px 0 8px 0;
            padding-bottom: 5px;
            border-bottom: 2.5px solid {_BRAND_PRIMARY};
        }}
        .report-title {{ font-size: {fp + 3}pt; font-weight: 700; color: {_BRAND_PRIMARY}; }}
        .report-subtitle {{ font-size: {fp}pt; color: #555; margin-top: 1px; }}
        .report-date {{ font-size: {fp - 1}pt; color: #666; margin-top: 2px; }}

        /* --- Section heading (separates table groups) --- */
        .section-heading {{
            font-size: {fp + 1}pt;
            font-weight: 700;
            color: {_BRAND_PRIMARY};
            margin: 14px 0 4px 0;
            padding: 4px 8px;
            background: {_BRAND_LIGHT};
            border-left: 3px solid {_BRAND_PRIMARY};
        }}

        /* --- Statement table --- */
        .stmt-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 4px;
            margin-bottom: 2px;
        }}
        col.col-ref {{ width: 52px; }}
        col.col-lbl {{ }}
        col.col-amt {{ width: 110px; }}

        .stmt-table th {{
            background: {_BRAND_PRIMARY};
            color: #fff;
            font-weight: 600;
            font-size: {fp - 1}pt;
            padding: 5px 8px;
            text-align: left;
            border: none;
        }}
        .stmt-table th.num {{ text-align: right; }}

        .stmt-table td {{
            padding: 2.5px 8px;
            font-size: {fp}pt;
            border-bottom: 1px solid #eee;
            vertical-align: top;
        }}
        .stmt-table td.ref {{
            color: #888;
            font-size: {fp - 1}pt;
            white-space: nowrap;
        }}
        .stmt-table td.num {{
            text-align: right;
            font-variant-numeric: tabular-nums;
            white-space: nowrap;
        }}

        /* --- Row kinds --- */
        tr.rk-section td {{
            font-weight: 700;
            background: {_SECTION_BG};
            font-size: {fp}pt;
            padding-top: 5px;
            padding-bottom: 5px;
            border-bottom: 1px solid {_BRAND_BORDER};
        }}
        tr.rk-group td {{
            font-weight: 600;
            padding-top: 4px;
        }}
        tr.rk-subsection td {{
            font-weight: 600;
        }}
        tr.rk-line td {{
            font-weight: 400;
        }}
        tr.rk-formula td,
        tr.rk-subtotal td {{
            font-weight: 700;
            background: {_SUBTOTAL_BG};
            border-top: 1.5px solid {_BRAND_BORDER};
            border-bottom: 1px solid {_BRAND_BORDER};
            padding-top: 3px;
            padding-bottom: 3px;
        }}
        tr.rk-total td {{
            font-weight: 700;
            background: {_TOTAL_BG};
            border-top: 2.5px double {_BRAND_PRIMARY};
            border-bottom: 2.5px double {_BRAND_PRIMARY};
            padding-top: 4px;
            padding-bottom: 4px;
            font-size: {fp}pt;
        }}
        tr.highlight td {{
            background: {_HIGHLIGHT_BG};
        }}
        tr.highlight.rk-formula td {{
            background: {_HIGHLIGHT_BG};
            border-top: 1.5px solid {_BRAND_BORDER};
        }}

        /* --- Summary table --- */
        .summary-table {{
            margin-top: 12px;
            border-collapse: collapse;
            width: auto;
            min-width: 320px;
            margin-left: auto;
            margin-right: 0;
        }}
        .summary-table td {{
            padding: 3px 12px;
            font-size: {fp}pt;
            border: none;
        }}
        .summary-table .summary-label {{
            font-weight: 600;
            text-align: left;
            padding-right: 24px;
        }}
        .summary-table .summary-value {{
            text-align: right;
            font-variant-numeric: tabular-nums;
            white-space: nowrap;
        }}
        .summary-table tr.summary-last td {{
            font-weight: 700;
            border-top: 1.5px solid {_BRAND_PRIMARY};
            padding-top: 5px;
        }}

        /* --- Footer --- */
        .footer {{
            margin-top: 14px;
            padding-top: 5px;
            border-top: 1px solid {_BRAND_BORDER};
            font-size: {fp - 2}pt;
            color: #999;
            text-align: center;
        }}
        """

    # ------------------------------------------------------------------
    # PDF rendering
    # ------------------------------------------------------------------

    def _render_to_pdf(
        self,
        html: str,
        output_path: str,
        page_size: StatementPageSize,
        orientation: StatementPageOrientation,
    ) -> None:
        """Render HTML to PDF via Chromium (WebDocumentRenderer).

        The @page CSS rule already declares page size and margins, so
        margin_mm=0 is passed to avoid double-margins.
        """
        from seeker_accounting.platform.printing.print_data_protocol import (
            PageOrientation,
            PageSize,
        )
        from seeker_accounting.platform.printing.web_renderer import WebDocumentRenderer

        ps = PageSize.A4 if page_size == StatementPageSize.A4 else PageSize.A5
        po = (
            PageOrientation.LANDSCAPE
            if orientation == StatementPageOrientation.LANDSCAPE
            else PageOrientation.PORTRAIT
        )

        renderer = WebDocumentRenderer()
        ok = renderer.render_pdf(
            html,
            output_path,
            page_size=ps,
            orientation=po,
            margin_mm=0,  # @page CSS rule handles margins
        )
        if not ok:
            raise RuntimeError(f"Chromium PDF rendering failed for: {output_path}")

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _fmt_amount(value: Decimal | None) -> str:
        if value is None:
            return ""
        if value == _ZERO:
            return "–"
        if value < 0:
            return f"({abs(value):,.2f})"
        return f"{value:,.2f}"
