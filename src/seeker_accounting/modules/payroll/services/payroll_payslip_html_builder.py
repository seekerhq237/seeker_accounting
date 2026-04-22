"""HTML builder for Seeker Accounting payslips.

Produces a complete, self-contained HTML document from a PayslipPrintDataDTO.
The HTML is the single source of truth — it drives both the live QWebEngineView
preview and the Chromium PDF export, guaranteeing pixel-perfect fidelity between
what you see and what you get.

Layout contract: the output is guaranteed to fit within one A4 page for any
realistic Cameroon-standard payslip (up to ~30 detail line items).

Design tokens are expressed as CSS custom properties for maintainability.
The HTML is intentionally self-contained (base64 logo, no network requests).
"""
from __future__ import annotations

import base64
import html
from decimal import Decimal
from pathlib import Path
from typing import Callable

from seeker_accounting.modules.payroll.dto.payroll_print_dto import PayslipPrintDataDTO


# ── Helpers ────────────────────────────────────────────────────────────────────

def _h(text: object) -> str:
    return html.escape(str(text) if text is not None else "")


def _fmt(value: Decimal | float | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.2f}"


def _logo_data_uri(logo_storage_path: str | None, resolver: Callable | None) -> str | None:
    """Resolve a logo storage path to an inline base64 data URI."""
    if not resolver or not logo_storage_path:
        return None
    try:
        resolved = resolver(logo_storage_path)
        if resolved is None:
            return None
        p = Path(resolved) if not isinstance(resolved, Path) else resolved
        if not p.exists():
            return None
        data = p.read_bytes()
        mime = {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "webp": "image/webp",
            "svg": "image/svg+xml",
        }.get(p.suffix.lower().lstrip("."), "image/png")
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:{mime};base64,{b64}"
    except Exception:
        return None


# ── CSS ────────────────────────────────────────────────────────────────────────
# All sizing is tuned so a full Cameroon payslip (earnings + deductions + taxes
# + employer charges ≈ 20+ line items) fits comfortably within one A4 page.
# @page margins: 12mm top/bottom, 14mm left/right → printable area 182×273mm.
# At 7.5pt (≈2.65mm) per detail row with 2px padding ≈ 3.5mm effective height,
# that leaves room for ~30 detail rows after all structural blocks.

_CSS = """/* ── Tokens ─────────────────────────────────────── */
:root {
  --c-primary: #2F4F6F;
  --c-primary-dark: #1E3A5F;
  --c-accent: #2E7D4F;
  --c-accent-bg: #EDF7F1;
  --c-accent-border: #C3DFD0;
  --c-tint: #EAF1F7;
  --c-border: #D6E0EA;
  --c-text: #1F2933;
  --c-muted: #6B7280;
  --c-faint: #9CA3AF;
  --c-stripe: #F6F8FB;
  --c-bg: #ffffff;
}

/* ── Reset & base ───────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html, body {
  font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
  font-size: 8pt;
  color: var(--c-text);
  background: var(--c-bg);
  line-height: 1.35;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}

/* ── Page layout ────────────────────────────────── */
@page {
  size: A4 portrait;
  margin: 12mm 14mm 12mm 14mm;
}

.page {
  width: 100%;
  max-width: 182mm;
  margin: 0 auto;
}

/* ── Banner ─────────────────────────────────────── */
.banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding-bottom: 6px;
  border-bottom: 2px solid var(--c-primary);
  margin-bottom: 8px;
}
.banner-logo {
  width: 38px; height: 38px;
  object-fit: contain; flex-shrink: 0;
}
.banner-name {
  flex: 1;
  font-size: 12pt; font-weight: 700; color: var(--c-primary);
  line-height: 1.15;
}
.banner-doc-title {
  font-size: 8pt; font-weight: 600;
  color: var(--c-muted); letter-spacing: 0.8px;
  line-height: 1.5; text-align: right; white-space: nowrap;
  text-transform: uppercase;
}

/* ── Identity grid (employer | employee) ───── */
.identity-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-bottom: 6px;
}
.id-card {
  border: 1px solid var(--c-border);
  border-radius: 3px;
  overflow: hidden;
}
.id-card-header {
  font-size: 6.5pt; font-weight: 700; color: var(--c-primary);
  background: var(--c-tint); padding: 3px 8px;
  border-bottom: 1px solid var(--c-border);
  letter-spacing: 0.5px; text-transform: uppercase;
}
.id-card-body { padding: 3px 8px 4px 8px; }
.idr {
  display: flex; align-items: baseline;
  padding: 1px 0;
}
.idr-lbl {
  font-size: 6.5pt; color: var(--c-muted);
  width: 100px; min-width: 100px;
  text-align: right; padding-right: 6px;
}
.idr-val {
  font-size: 7.5pt; font-weight: 600; color: var(--c-text);
  flex: 1;
}

/* ── Context bar ────────────────────────────────── */
.context-bar {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  background: var(--c-tint); border-radius: 3px;
  margin-bottom: 8px;
  padding: 4px 0;
}
.ctx-cell {
  text-align: center; padding: 1px 6px;
}
.ctx-cell + .ctx-cell {
  border-left: 1px solid var(--c-border);
}
.ctx-lbl { font-size: 6pt; color: var(--c-muted); display: block; text-transform: uppercase; letter-spacing: 0.3px; }
.ctx-val { font-size: 7.5pt; font-weight: 600; color: var(--c-text); display: block; }

/* ── Sections ───────────────────────────────────── */
.section-title {
  font-size: 7.5pt; font-weight: 700; color: var(--c-primary);
  letter-spacing: 0.3px;
  border-bottom: 1.5px solid var(--c-primary);
  padding: 0 0 2px 0; margin: 6px 0 2px 0;
}
table.detail {
  width: 100%; border-collapse: collapse;
  font-size: 7.5pt; margin-bottom: 4px;
}
table.detail td {
  padding: 1.5px 6px;
  border-bottom: 1px solid #EEF1F4;
}
table.detail td.num {
  text-align: right; width: 110px;
  font-variant-numeric: tabular-nums;
}
table.detail tr:nth-child(even) td { background: var(--c-stripe); }
table.detail tr:nth-child(odd)  td { background: var(--c-bg); }
table.detail tr.subtotal-row td {
  font-weight: 700; background: var(--c-tint) !important;
  border-top: 1.5px solid var(--c-primary);
  color: var(--c-primary); padding-top: 3px; padding-bottom: 3px;
  font-size: 7.5pt;
}

/* ── Statutory bases strip ──────────────────────── */
.bases-strip {
  display: grid; grid-template-columns: repeat(3, 1fr);
  gap: 6px; margin: 6px 0 8px 0;
}
.base-block {
  background: var(--c-tint); border: 1px solid var(--c-border);
  border-radius: 3px; text-align: center; padding: 4px 6px;
}
.base-lbl { font-size: 6pt; color: var(--c-muted); text-transform: uppercase; letter-spacing: 0.4px; }
.base-val { font-size: 8.5pt; font-weight: 700; color: var(--c-primary);
    font-variant-numeric: tabular-nums; }

/* ── Net pay panel ──────────────────────────────── */
.net-panel {
  background: var(--c-accent-bg); border: 1.5px solid var(--c-accent-border);
  border-radius: 4px; padding: 6px 14px;
  margin: 8px 0;
  break-inside: avoid;
}
.net-row {
  display: flex; align-items: baseline; justify-content: space-between;
  gap: 8px;
}
.net-row + .net-row {
  border-top: 1px solid var(--c-accent-border);
  margin-top: 4px; padding-top: 4px;
}
.net-lbl { font-size: 7.5pt; color: var(--c-accent); }
.net-lbl-main { font-size: 9pt; font-weight: 700; color: var(--c-accent); }
.net-amt { font-size: 7.5pt; font-weight: 600; color: var(--c-accent);
    font-variant-numeric: tabular-nums; text-align: right; white-space: nowrap; }
.net-amt-main { font-size: 14pt; font-weight: 800; color: var(--c-accent);
    font-variant-numeric: tabular-nums; text-align: right; white-space: nowrap;
    letter-spacing: 0.3px; }

/* ── Signature block ────────────────────────────── */
.sig-table {
  width: 100%; border-collapse: collapse;
  margin-top: 16px; font-size: 6.5pt; color: var(--c-muted);
}
.sig-table td { width: 33%; padding: 0 8px; text-align: center; vertical-align: bottom; }
.sig-line { border-top: 1px solid var(--c-faint); margin-top: 22px; padding-top: 3px; }

/* ── Footer ─────────────────────────────────────── */
.footer {
  font-size: 6.5pt; color: var(--c-faint); text-align: right;
  margin-top: 8px; border-top: 1px solid #EEF1F4; padding-top: 3px;
}

/* ── Warning bar ────────────────────────────────── */
.warning-bar {
  padding: 4px 8px; background: #FFF8E1;
  border-left: 3px solid #F9A825;
  font-size: 7pt; color: #6D4C00; margin-bottom: 6px;
}

/* ── Print helpers ──────────────────────────────── */
.no-break { break-inside: avoid; }

@media print {
  body { background: #ffffff; }
  .no-print { display: none; }
  table.detail tr:nth-child(even) td { background: var(--c-stripe) !important; }
  table.detail tr.subtotal-row td { background: var(--c-tint) !important; }
  .net-panel { background: var(--c-accent-bg) !important; }
  .base-block { background: var(--c-tint) !important; }
  .context-bar { background: var(--c-tint) !important; }
  .id-card-header { background: var(--c-tint) !important; }
}
"""


# ── Builder ────────────────────────────────────────────────────────────────────────

class PayslipHtmlBuilder:
    """Builds a complete self-contained HTML payslip from a PayslipPrintDataDTO.

    No external dependencies — the builder is stateless and can be constructed
    directly.  Pass a ``logo_resolver`` callable to embed the company logo.

    Usage::

        builder = PayslipHtmlBuilder(logo_resolver=svc.resolve_logo_path)
        html_str = builder.build(print_dto)
    """

    def __init__(
        self,
        logo_resolver: Callable[[str | None], object | None] | None = None,
    ) -> None:
        self._logo_resolver = logo_resolver

    # ── Public entry point ─────────────────────────────────────────────────────

    def build(
        self,
        ps: PayslipPrintDataDTO,
        *,
        warning_lines: list[str] | None = None,
    ) -> str:
        """Return a complete HTML document string for the given payslip."""
        logo_uri = _logo_data_uri(ps.company_logo_storage_path, self._logo_resolver)
        parts: list[str] = []

        parts.append(self._doc_open())
        parts.append('<div class="page">')

        for msg in (warning_lines or []):
            parts.append(f'<div class="warning-bar">{_h(msg)}</div>')

        parts.append(self._banner(ps, logo_uri))
        parts.append(self._identity_grid(ps))
        parts.append(self._context_bar(ps))

        parts.append(self._section(
            "EARNINGS / RÉMUNÉRATIONS",
            ps.earnings,
            ps.gross_earnings,
            subtotal_label="Gross Earnings / Salaire Brut",
        ))

        parts.append(self._bases_strip(ps))

        parts.append(self._section(
            "EMPLOYEE DEDUCTIONS / RETENUES SALARIALES",
            ps.deductions,
            ps.total_deductions,
            subtotal_label="Total Deductions / Total Retenues",
        ))

        parts.append(self._section(
            "TAXES / IMPÔTS",
            ps.taxes,
            ps.total_taxes,
            subtotal_label="Total Taxes / Total Impôts",
        ))

        parts.append(self._net_panel(ps))

        parts.append(self._section(
            "EMPLOYER CHARGES / CHARGES PATRONALES",
            ps.employer_contributions,
            ps.total_employer_contributions,
            subtotal_label="Total Employer Charges / Total Charges",
        ))

        parts.append(self._signature_block())
        parts.append(self._footer(ps))

        parts.append("</div>")  # .page
        parts.append("</body></html>")

        return "".join(parts)

    # ── Private builders ───────────────────────────────────────────────────────

    def _doc_open(self) -> str:
        return (
            '<!DOCTYPE html><html lang="en"><head>'
            '<meta charset="UTF-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
            f"<style>{_CSS}</style>"
            "</head><body>"
        )

    def _banner(self, ps: PayslipPrintDataDTO, logo_uri: str | None) -> str:
        logo_html = (
            f'<img class="banner-logo" src="{logo_uri}" alt="">'
            if logo_uri
            else ""
        )
        return (
            '<div class="banner">'
            f"{logo_html}"
            f'<div class="banner-name">{_h(ps.company_name)}</div>'
            '<div class="banner-doc-title">Bulletin de Paie<br>Payslip</div>'
            "</div>"
        )

    def _identity_grid(self, ps: PayslipPrintDataDTO) -> str:
        hire_str = (
            ps.employee_hire_date.strftime("%d/%m/%Y")
            if ps.employee_hire_date
            else None
        )

        employer_rows = [
            ("Company", ps.company_name),
            ("Address", ps.company_address),
            ("City / Ville", ps.company_city),
            ("Tax ID / NIU", ps.company_tax_identifier),
            ("CNPS No.", ps.company_cnps_employer_number),
            ("Phone", ps.company_phone),
        ]
        employee_rows = [
            ("Name / Nom", ps.employee_display_name),
            ("No. / Matricule", ps.employee_number),
            ("Position / Fonction", ps.employee_position),
            ("Department", ps.employee_department),
            ("NIF", ps.employee_nif),
            ("CNPS No.", ps.employee_cnps_number),
            ("Hire / Embauche", hire_str),
        ]

        def _card(title: str, rows: list) -> str:
            rows_html = "".join(
                f'<div class="idr">'
                f'<span class="idr-lbl">{_h(lbl)}:</span>'
                f'<span class="idr-val">{_h(val) if val else "—"}</span>'
                f"</div>"
                for lbl, val in rows
            )
            return (
                '<div class="id-card">'
                f'<div class="id-card-header">{_h(title)}</div>'
                f'<div class="id-card-body">{rows_html}</div>'
                "</div>"
            )

        return (
            '<div class="identity-grid">'
            + _card("Employer / Employeur", employer_rows)
            + _card("Employee / Employé(e)", employee_rows)
            + "</div>"
        )

    def _context_bar(self, ps: PayslipPrintDataDTO) -> str:
        pay_mode_map = {
            "bank": "Bank Transfer",
            "cash": "Cash",
            "petty_cash": "Petty Cash",
        }
        if ps.payment_account_name:
            mode_label = pay_mode_map.get(
                ps.payment_account_type or "", ps.payment_account_type or "Payment"
            )
            acct = ps.payment_account_name
            if ps.payment_account_reference:
                acct = f"{acct} ({ps.payment_account_reference})"
            payment_cell = (mode_label, acct)
        else:
            payment_cell = ("Payment", "—")

        pay_date = (
            ps.payment_date.strftime("%d/%m/%Y") if ps.payment_date else "—"
        )

        cells = [
            ("Pay Period", ps.period_label or "—"),
            ("Payment Date", pay_date),
            ("Run Reference", ps.run_reference or "—"),
            payment_cell,
        ]

        cells_html = "".join(
            f'<div class="ctx-cell">'
            f'<span class="ctx-lbl">{_h(lbl)}</span>'
            f'<span class="ctx-val">{_h(val)}</span>'
            f"</div>"
            for lbl, val in cells
        )
        return f'<div class="context-bar">{cells_html}</div>'

    def _section(
        self,
        title: str,
        lines: tuple,
        subtotal: Decimal,
        *,
        subtotal_label: str = "Subtotal",
    ) -> str:
        if not lines:
            return ""

        rows_html = "".join(
            f"<tr>"
            f'<td>{_h(name)}</td>'
            f'<td class="num">{_fmt(amount)}</td>'
            f"</tr>"
            for name, amount in lines
        )

        subtotal_row = (
            f'<tr class="subtotal-row">'
            f"<td>{_h(subtotal_label)}</td>"
            f'<td class="num">{_fmt(subtotal)}</td>'
            f"</tr>"
        )

        return (
            f'<div class="no-break">'
            f'<div class="section-title">{_h(title)}</div>'
            f'<table class="detail"><tbody>'
            f"{rows_html}"
            f"{subtotal_row}"
            f"</tbody></table>"
            f"</div>"
        )

    def _bases_strip(self, ps: PayslipPrintDataDTO) -> str:
        blocks = [
            ("CNPS Base", ps.cnps_contributory_base),
            ("Taxable Base (IRPP)", ps.taxable_salary_base),
            ("TDL Base", ps.tdl_base),
        ]
        blocks_html = "".join(
            f'<div class="base-block">'
            f'<div class="base-lbl">{_h(lbl)}</div>'
            f'<div class="base-val">{_fmt(val)}</div>'
            f"</div>"
            for lbl, val in blocks
        )
        return f'<div class="bases-strip">{blocks_html}</div>'

    def _net_panel(self, ps: PayslipPrintDataDTO) -> str:
        net_taxable = ps.taxable_salary_base - ps.total_deductions
        ccy = _h(ps.currency_code)
        return (
            '<div class="net-panel">'
            '<div class="net-row">'
            '<span class="net-lbl">Net Taxable / Salaire Net Imposable</span>'
            f'<span class="net-amt">{_fmt(net_taxable)} {ccy}</span>'
            "</div>"
            '<div class="net-row">'
            '<span class="net-lbl-main">NET PAYABLE / NET À PAYER</span>'
            f'<span class="net-amt-main">{_fmt(ps.net_payable)} {ccy}</span>'
            "</div>"
            "</div>"
        )

    def _signature_block(self) -> str:
        sigs = [
            "Prepared by / Établi par",
            "Approved by / Approuvé par",
            "Employee / Employé(e)",
        ]
        cells = "".join(
            f'<td><div class="sig-line">{_h(s)}</div></td>' for s in sigs
        )
        return f'<table class="sig-table"><tr>{cells}</tr></table>'

    def _footer(self, ps: PayslipPrintDataDTO) -> str:
        from datetime import datetime

        generated = datetime.now().strftime("%d/%m/%Y %H:%M")
        return (
            f'<div class="footer">'
            f"{_h(ps.currency_code)} &middot; Generated {generated} &middot; Seeker Accounting"
            f"</div>"
        )
