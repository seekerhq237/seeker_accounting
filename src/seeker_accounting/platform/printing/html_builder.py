"""Shared HTML/CSS template utilities for PDF document rendering.

All PDFs in Seeker Accounting are rendered via Qt's QPrinter + QTextDocument
(HTML to PDF). This module provides the shared visual language:

  - Company header with optional logo
  - Branded footer
  - A4/A5-aware CSS
  - Reusable table and section builders
"""
from __future__ import annotations

import base64
import html as _html_module
import os
from datetime import datetime
from decimal import Decimal

from seeker_accounting.platform.printing.print_data_protocol import (
    CompanyHeaderData,
    PageSize,
)

_BRAND_PRIMARY = "#1e3a5f"
_BRAND_LIGHT = "#f0f3f7"
_BRAND_BORDER = "#d0d7de"
_BRAND_TEXT_MUTED = "#6b7280"

_BRAND_NAME = "Seeker Accounting"
_BRAND_TAGLINE = "Built for Business Clarity. Designed For Success."


def h(text: object) -> str:
    """HTML-escape a value for safe insertion."""
    return _html_module.escape(str(text))


def fmt_decimal(value: Decimal | float | None, decimals: int = 2) -> str:
    """Format a numeric value with thousand separators."""
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return f"{value:,.{decimals}f}"
    return f"{float(value):,.{decimals}f}"


def _get_base_css(page_size: PageSize) -> str:
    """Return the full base CSS adapted for A4 or A5."""
    fs = page_size.body_font_size_pt
    margin_mm = page_size.margin_mm
    w_mm, h_mm = page_size.dimensions_mm

    return f"""\
@page {{
    size: {w_mm}mm {h_mm}mm;
    margin: {margin_mm}mm;
}}
* {{ box-sizing: border-box; }}
html, body {{ height: 100%; }}
body {{
    font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: {fs}pt;
    color: #1a1a1a;
    margin: 0;
    padding: 0;
    line-height: 1.48;
}}
.page-shell {{
    display: table;
    width: 100%;
    min-height: 100%;
    border-collapse: collapse;
}}
.page-content {{
    display: table-row;
    height: 100%;
}}
.page-footer-row {{
    display: table-row;
}}

.co-header {{
    margin-bottom: 14px;
    padding-bottom: 10px;
    border-bottom: 1px solid {_BRAND_BORDER};
    display: table;
    width: 100%;
}}
.co-header-left {{
    display: table-cell;
    vertical-align: top;
    padding-right: 14px;
}}
.co-header-right {{
    display: table-cell;
    vertical-align: top;
    text-align: right;
    width: 1%;
    white-space: nowrap;
}}
.co-logo-wrap {{ margin-bottom: 6px; }}
.co-name {{
    font-size: {fs + 5}pt;
    font-weight: 700;
    color: {_BRAND_PRIMARY};
    margin: 0 0 2px 0;
    line-height: 1.18;
}}
.co-legal {{
    font-size: {fs - 1}pt;
    color: {_BRAND_TEXT_MUTED};
    margin: 0 0 4px 0;
}}
.co-address {{
    font-size: {fs - 1}pt;
    color: #374151;
    line-height: 1.45;
}}
.co-meta {{
    font-size: {fs - 1}pt;
    color: {_BRAND_TEXT_MUTED};
    line-height: 1.5;
    margin-top: 4px;
}}
.co-logo {{
    display: block;
    margin-left: auto;
    max-height: 72px;
    max-width: 170px;
    object-fit: contain;
}}

.doc-title-block {{
    margin-bottom: 12px;
    padding: 0 0 8px 0;
    background: transparent;
    border-bottom: 1px solid {_BRAND_BORDER};
}}
.doc-title {{
    font-size: {fs + 3}pt;
    font-weight: 700;
    color: {_BRAND_PRIMARY};
    margin: 0 0 2px 0;
}}
.doc-meta-row {{
    font-size: {fs - 1}pt;
    color: {_BRAND_TEXT_MUTED};
}}
.doc-meta-row span {{
    margin-right: 18px;
}}

.kv-grid {{
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 12px;
    font-size: {fs - 0.5}pt;
}}
.kv-grid td {{
    padding: 2px 12px 2px 0;
    vertical-align: top;
}}
.kv-label {{
    font-size: {round(fs * 0.82)}pt;
    color: {_BRAND_TEXT_MUTED};
    text-transform: uppercase;
    letter-spacing: 0.35px;
    white-space: nowrap;
    padding-right: 8px !important;
}}
.kv-value {{
    font-size: {fs - 1}pt;
    font-weight: 600;
    color: #1a1a1a;
}}

.chip {{
    display: inline-block;
    padding: 1px 7px;
    border-radius: 10px;
    font-size: {round(fs * 0.80)}pt;
    font-weight: 600;
    letter-spacing: 0.25px;
}}
.chip-draft {{ background: #f0f0f0; color: #555; }}
.chip-posted {{ background: #e6f4ea; color: #1e6b3a; }}
.chip-cancelled {{ background: #fde8e8; color: #9b1c1c; }}
.chip-paid {{ background: #e6f4ea; color: #1e6b3a; }}
.chip-partial {{ background: #fff3cd; color: #856404; }}
.chip-unpaid {{ background: #fff0f0; color: #9b1c1c; }}

.section-title {{
    font-size: {fs}pt;
    font-weight: 700;
    color: {_BRAND_PRIMARY};
    margin: 14px 0 6px 0;
    padding-bottom: 2px;
    border-bottom: 1px solid {_BRAND_BORDER};
}}

table.data-table {{
    border-collapse: collapse;
    width: 100%;
    font-size: {fs - 1}pt;
    margin-bottom: 12px;
}}
table.data-table thead {{
    display: table-header-group;
}}
table.data-table tr {{
    page-break-inside: avoid;
}}
table.data-table th {{
    background-color: {_BRAND_LIGHT};
    color: {_BRAND_PRIMARY};
    padding: 5px 8px;
    font-size: {round(fs * 0.85)}pt;
    font-weight: 700;
    text-align: left;
    border-top: 1px solid {_BRAND_BORDER};
    border-bottom: 1px solid {_BRAND_BORDER};
    white-space: nowrap;
}}
table.data-table th.num {{ text-align: right; }}
table.data-table td {{
    padding: 5px 8px;
    border-bottom: 1px solid #e8edf3;
    vertical-align: top;
    overflow-wrap: break-word;
}}
table.data-table td.num {{
    text-align: right;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
}}
table.data-table th.nowrap,
table.data-table td.nowrap {{
    white-space: nowrap;
}}
table.data-table tr.even {{ background: #ffffff; }}
table.data-table tr.odd {{ background: #fbfcfe; }}
table.data-table tr.total-row td {{
    font-weight: 700;
    border-top: 1.5px solid {_BRAND_PRIMARY};
    background: #f7f9fc;
}}
table.data-table tr.subtotal-row td {{
    font-weight: 600;
    background: {_BRAND_LIGHT};
    border-top: 1px solid {_BRAND_BORDER};
}}
table.data-table td.total-label {{
    color: {_BRAND_PRIMARY};
    text-transform: uppercase;
    letter-spacing: 0.35px;
}}
table.data-table td.empty {{
    color: transparent;
}}

.summary-box {{
    margin: 10px 0;
    border: 1px solid {_BRAND_BORDER};
    border-radius: 4px;
    overflow: hidden;
}}
.summary-box table {{
    width: 100%;
    border-collapse: collapse;
    font-size: {fs - 1}pt;
}}
.summary-box td {{
    padding: 6px 12px;
    border-bottom: 1px solid #edf2f7;
}}
.summary-box td.num {{
    text-align: right;
    font-variant-numeric: tabular-nums;
    font-weight: 600;
}}
.summary-box tr:last-child td {{
    border-bottom: none;
}}
.summary-box tr.highlight td {{
    background: {_BRAND_LIGHT};
    font-weight: 700;
    font-size: {fs}pt;
    color: {_BRAND_PRIMARY};
}}

.net-box {{
    margin: 12px 0;
    padding: 10px 14px;
    background: #e8f5e9;
    border-left: 4px solid #2e7d32;
    border-radius: 2px;
}}
.net-box .net-label {{ font-size: {fs - 1}pt; font-weight: 600; color: #1b5e20; }}
.net-box .net-amount {{ font-size: {fs + 3}pt; font-weight: 700; color: #1b5e20; }}

.warning-bar {{
    padding: 6px 10px;
    background: #fff8e1;
    border-left: 3px solid #f9a825;
    font-size: {fs - 1}pt;
    color: #6d4c00;
    margin-bottom: 10px;
}}

.page-break {{ page-break-before: always; }}

.sk-footer {{
    padding-top: 8px;
    border-top: 1px solid {_BRAND_BORDER};
    display: table;
    width: 100%;
}}
.sk-footer-brand {{ display: table-cell; vertical-align: bottom; }}
.sk-footer-meta {{ display: table-cell; vertical-align: bottom; text-align: right; }}
.sk-brand-name {{
    font-size: {round(fs * 0.82)}pt;
    font-weight: 700;
    color: {_BRAND_PRIMARY};
    letter-spacing: 0.25px;
}}
.sk-brand-tagline {{
    display: block;
    font-size: {round(fs * 0.72)}pt;
    color: {_BRAND_TEXT_MUTED};
    margin-top: 1px;
}}
.sk-footer-ts {{
    font-size: {round(fs * 0.72)}pt;
    color: {_BRAND_TEXT_MUTED};
}}
"""


def _logo_img_tag(logo_path: str) -> str:
    """Return an <img> tag with inline base64 PNG/JPEG, or empty string on error."""
    if not logo_path or not os.path.isfile(logo_path):
        return ""
    try:
        ext = os.path.splitext(logo_path)[1].lower().lstrip(".")
        mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}.get(ext, "image/png")
        with open(logo_path, "rb") as stream:
            data = base64.b64encode(stream.read()).decode()
        return f'<img src="data:{mime};base64,{data}" class="co-logo" alt="Company logo" />'
    except OSError:
        return ""


def build_company_header(company: CompanyHeaderData) -> str:
    """Build the company identity header used at the top of every document."""
    left_parts: list[str] = [f'<div class="co-name">{h(company.name)}</div>']
    if company.legal_name and company.legal_name != company.name:
        left_parts.append(f'<div class="co-legal">{h(company.legal_name)}</div>')

    if company.address_block:
        address_html = "<br/>".join(h(line) for line in company.address_block)
        left_parts.append(f'<div class="co-address">{address_html}</div>')

    right_parts: list[str] = []
    logo_tag = _logo_img_tag(company.logo_path or "")
    if logo_tag:
        right_parts.append(f'<div class="co-logo-wrap">{logo_tag}</div>')

    meta_lines: list[str] = []
    if company.tax_identifier:
        meta_lines.append(f"Tax ID: {h(company.tax_identifier)}")
    if company.registration_number:
        meta_lines.append(f"Reg: {h(company.registration_number)}")
    if company.phone:
        meta_lines.append(h(company.phone))
    if company.email:
        meta_lines.append(h(company.email))
    if meta_lines:
        right_parts.append(f'<div class="co-meta">{"<br/>".join(meta_lines)}</div>')

    parts = ['<div class="co-header">', f'<div class="co-header-left">{"".join(left_parts)}</div>']
    if right_parts:
        parts.append(f'<div class="co-header-right">{"".join(right_parts)}</div>')
    parts.append("</div>")
    return "".join(parts)


def build_document_title_block(
    title: str,
    *,
    subtitle: str | None = None,
    meta_pairs: list[tuple[str, str]] | None = None,
) -> str:
    """Build the document title block."""
    parts: list[str] = [
        '<div class="doc-title-block">',
        f'<div class="doc-title">{h(title)}</div>',
    ]
    if subtitle:
        parts.append(f'<div class="doc-meta-row">{h(subtitle)}</div>')
    if meta_pairs:
        spans = "".join(f"<span><b>{h(key)}:</b> {h(value)}</span>" for key, value in meta_pairs)
        parts.append(f'<div class="doc-meta-row">{spans}</div>')
    parts.append("</div>")
    return "".join(parts)


def build_key_value_grid(
    pairs: list[tuple[str, str]],
    columns: int = 3,
) -> str:
    """Build a responsive key-value metadata grid."""
    rows: list[str] = []
    for index in range(0, len(pairs), columns):
        chunk = pairs[index : index + columns]
        cells = "".join(
            f'<td class="kv-label" width="{100 // columns // 2}%">{h(label)}</td>'
            f'<td class="kv-value" width="{100 // columns // 2}%">{h(value)}</td>'
            for label, value in chunk
        )
        rows.append(f"<tr>{cells}</tr>")
    return f'<table class="kv-grid">{"".join(rows)}</table>'


def build_section_title(title: str) -> str:
    """Render a section heading."""
    return f'<div class="section-title">{h(title)}</div>'


def build_data_table(
    columns: list[str],
    rows: list[list[str]],
    *,
    numeric_columns: set[int] | None = None,
    total_row: list[str] | None = None,
    subtotal_rows: dict[int, list[str]] | None = None,
    nowrap_columns: set[int] | None = None,
    column_widths: dict[int, str] | None = None,
) -> str:
    """Build a professional data table."""
    numeric = numeric_columns or set()
    nowrap = set(nowrap_columns or set()) | set(numeric)
    subtotals = subtotal_rows or {}

    def _is_blank(value: object) -> bool:
        return str(value).strip() == ""

    def _cell_attrs(index: int, *, extra_classes: list[str] | None = None) -> str:
        classes = list(extra_classes or [])
        if index in numeric:
            classes.append("num")
        if index in nowrap:
            classes.append("nowrap")

        attrs: list[str] = []
        if classes:
            attrs.append(f'class="{" ".join(classes)}"')
        if column_widths and index in column_widths:
            attrs.append(f'style="width: {h(column_widths[index])};"')
        return f" {' '.join(attrs)}" if attrs else ""

    def _regular_cells(row: list[str]) -> str:
        return "".join(f"<td{_cell_attrs(index)}>{h(value)}</td>" for index, value in enumerate(row))

    def _total_cells(row: list[str]) -> str:
        non_empty_indices = [index for index, value in enumerate(row) if not _is_blank(value)]
        if not non_empty_indices:
            return f'<td class="empty" colspan="{len(columns)}"></td>'
        if len(non_empty_indices) == 1:
            only_index = non_empty_indices[0]
            return (
                f'<td{_cell_attrs(only_index, extra_classes=["total-label"])} '
                f'colspan="{len(columns)}">{h(row[only_index])}</td>'
            )

        first_non_empty = non_empty_indices[0]
        parts: list[str] = []
        index = 0
        while index < len(row):
            if _is_blank(row[index]):
                end = index
                while end < len(row) and _is_blank(row[end]):
                    end += 1
                parts.append(f'<td class="empty" colspan="{end - index}"></td>')
                index = end
                continue

            extra_classes = ["total-label"] if index == first_non_empty and index not in numeric else []
            parts.append(f"<td{_cell_attrs(index, extra_classes=extra_classes)}>{h(row[index])}</td>")
            index += 1
        return "".join(parts)

    header_cells = "".join(f"<th{_cell_attrs(index)}>{h(column)}</th>" for index, column in enumerate(columns))

    body_parts: list[str] = []
    for row_index, row in enumerate(rows):
        if row_index in subtotals:
            body_parts.append(f'<tr class="subtotal-row">{_regular_cells(subtotals[row_index])}</tr>')

        row_class = "even" if row_index % 2 == 0 else "odd"
        body_parts.append(f'<tr class="{row_class}">{_regular_cells(row)}</tr>')

    total_html = ""
    if total_row:
        total_html = f'<tr class="total-row">{_total_cells(total_row)}</tr>'

    return (
        '<table class="data-table">'
        "<thead>"
        f"<tr>{header_cells}</tr>"
        "</thead>"
        "<tbody>"
        f"{''.join(body_parts)}"
        f"{total_html}"
        "</tbody>"
        "</table>"
    )


def build_summary_box(pairs: list[tuple[str, str]], *, highlight_last: bool = True) -> str:
    """Build a summary box."""
    rows: list[str] = []
    for index, (label, value) in enumerate(pairs):
        row_class = ' class="highlight"' if highlight_last and index == len(pairs) - 1 else ""
        rows.append(
            f"<tr{row_class}>"
            f"<td>{h(label)}</td>"
            f'<td class="num">{h(value)}</td>'
            "</tr>"
        )
    return '<div class="summary-box"><table>' + "".join(rows) + "</table></div>"


def build_branded_footer(generated_at: str | None = None) -> str:
    """Build the Seeker Accounting branded footer shown on every document."""
    timestamp = generated_at or datetime.now().strftime("%Y-%m-%d %H:%M")
    return (
        '<div class="sk-footer">'
        '<div class="sk-footer-brand">'
        f'<span class="sk-brand-name">{h(_BRAND_NAME)}</span>'
        f'<span class="sk-brand-tagline">{h(_BRAND_TAGLINE)}</span>'
        "</div>"
        '<div class="sk-footer-meta">'
        f'<span class="sk-footer-ts">Generated: {h(timestamp)}</span>'
        "</div>"
        "</div>"
    )


def wrap_html(
    body_html: str,
    *,
    page_size: PageSize = PageSize.A4,
    extra_css: str = "",
) -> str:
    """Wrap body HTML with full document structure, base CSS, and footer."""
    css = _get_base_css(page_size)
    if extra_css:
        css += "\n" + extra_css

    footer_html = build_branded_footer()
    return (
        "<!DOCTYPE html>"
        "<html><head>"
        '<meta charset="utf-8"/>'
        f"<style>{css}</style>"
        "</head>"
        "<body>"
        '<div class="page-shell">'
        f'<div class="page-content">{body_html}</div>'
        f'<div class="page-footer-row">{footer_html}</div>'
        "</div>"
        "</body>"
        "</html>"
    )
