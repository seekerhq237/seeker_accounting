"""Tax return PDF export service (T24).

Renders a posted tax return into a DGI-form-faithful printable PDF
using the existing Qt-based print engine (no external PDF library
required).

For VAT returns the PDF mirrors the official Cameroon DGI VAT page
(Sections 4 \u2014 8 with statutory line codes L17-L47), driven by
the shared ``vat_return_form_layout`` read model that the on-screen
viewer also uses.

For non-VAT (assessed) returns \u2014 Patente / TSR / Customs / CIT \u2014
the PDF stays compact: tax-payer header, a single "Assessed Amount"
panel, and totals.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from html import escape
from typing import TYPE_CHECKING, Callable

from sqlalchemy.orm import Session

from seeker_accounting.app.context.app_context import AppContext
from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import (
    PermissionService,
)
from seeker_accounting.modules.companies.repositories.company_repository import (
    CompanyRepository,
)
from seeker_accounting.modules.taxation.constants import TAX_TYPE_VAT
from seeker_accounting.modules.taxation.repositories.company_tax_profile_repository import (
    CompanyTaxProfileRepository,
)
from seeker_accounting.modules.taxation.dto.tax_compliance_dto import (
    ExportTaxReturnPDFCommand,
    ExportTaxReturnPDFResultDTO,
    TaxReturnDTO,
    TaxReturnLineDTO,
)
from seeker_accounting.modules.taxation.repositories.tax_return_repository import (
    TaxReturnRepository,
)
from seeker_accounting.modules.taxation.services.vat_return_form_layout import (
    VATFormLayout,
    VATFormRow,
    VATFormSection,
    build_vat_form_layout,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService
    from seeker_accounting.platform.printing.print_engine import PrintEngine


TaxReturnRepositoryFactory = Callable[[Session], TaxReturnRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
CompanyTaxProfileRepositoryFactory = Callable[[Session], CompanyTaxProfileRepository]


_DASH = "\u2014"


def _fmt_amount(value: Decimal | None) -> str:
    if value is None:
        return _DASH
    quantized = Decimal(value).quantize(Decimal("0.01"))
    return f"{quantized:,.2f}"


def _esc(value: str | None) -> str:
    return escape(value or "")


class TaxReturnPDFExportService:
    """Generate a printable PDF for a tax return."""

    PERMISSION_EXPORT = "taxation.returns.export_pdf"

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        app_context: AppContext,
        tax_return_repository_factory: TaxReturnRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        permission_service: PermissionService,
        print_engine: "PrintEngine",
        audit_service: "AuditService | None" = None,
        company_tax_profile_repository_factory: CompanyTaxProfileRepositoryFactory | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._app_context = app_context
        self._tax_return_repository_factory = tax_return_repository_factory
        self._company_repository_factory = company_repository_factory
        self._permission_service = permission_service
        self._print_engine = print_engine
        self._audit_service = audit_service
        self._company_tax_profile_repository_factory = company_tax_profile_repository_factory

    # ---------------- Public ----------------

    def export(
        self,
        company_id: int,
        command: ExportTaxReturnPDFCommand,
    ) -> ExportTaxReturnPDFResultDTO:
        self._permission_service.require_permission(self.PERMISSION_EXPORT)

        output_path = (command.output_path or "").strip()
        if not output_path:
            raise ValidationError("Output path is required.")
        if not output_path.lower().endswith(".pdf"):
            raise ValidationError("Tax return PDF output path must end with .pdf.")

        with self._unit_of_work_factory() as uow:
            company_repo = self._company_repository_factory(uow.session)
            company = company_repo.get_by_id(company_id)
            if company is None:
                raise NotFoundError(f"Company {company_id} not found.")

            return_repo = self._tax_return_repository_factory(uow.session)
            tax_return = return_repo.get_by_id(company_id, command.return_id)
            if tax_return is None:
                raise NotFoundError(
                    f"Tax return {command.return_id} not found for company {company_id}."
                )

            # T46: load tax profile for regime checkbox and supplementary fields
            tax_profile = None
            if self._company_tax_profile_repository_factory is not None:
                profile_repo = self._company_tax_profile_repository_factory(uow.session)
                tax_profile = profile_repo.get_by_company(company_id)

            company_snapshot = self._snapshot_company(company, tax_profile)
            return_dto = self._snapshot_return(tax_return)

        html = self._render_html(company_snapshot, return_dto)
        self._print_engine.render_pdf(html, output_path)
        self._record_audit(company_id, command.return_id, output_path)

        return ExportTaxReturnPDFResultDTO(
            return_id=command.return_id,
            output_path=output_path,
            rendered_at=datetime.utcnow(),
        )

    # ---------------- Snapshots (decouple from session) ----------------

    @staticmethod
    def _snapshot_company(company, tax_profile=None) -> dict[str, str | None]:
        addr_parts = [
            getattr(company, "address_line_1", None),
            getattr(company, "address_line_2", None),
            getattr(company, "city", None),
            getattr(company, "region", None),
        ]
        addr = ", ".join(p for p in addr_parts if p)
        # Prefer NIU from tax profile; fall back to company.tax_identifier
        niu = (
            getattr(tax_profile, "niu", None)
            if tax_profile is not None
            else None
        ) or getattr(company, "tax_identifier", None)
        return {
            "name": (
                getattr(company, "display_name", None)
                or getattr(company, "legal_name", "")
                or ""
            ),
            "legal_name": getattr(company, "legal_name", None),
            "tax_id": niu,
            "registration_number": getattr(company, "registration_number", None),
            "address": addr or None,
            "phone": getattr(company, "phone", None),
            "email": getattr(company, "email", None),
            # T46 tax-profile fields
            "tax_regime_code": (
                getattr(tax_profile, "tax_regime_code", None)
                if tax_profile is not None
                else None
            ),
            "tax_center_code": (
                getattr(tax_profile, "tax_center_code", None)
                if tax_profile is not None
                else None
            ),
            "taxpayer_segment_code": (
                getattr(tax_profile, "taxpayer_segment_code", None)
                if tax_profile is not None
                else None
            ),
        }

    @staticmethod
    def _snapshot_return(tax_return) -> TaxReturnDTO:
        # Minimal snapshot \u2014 we only need fields the layout uses.
        lines = tuple(
            TaxReturnLineDTO(
                id=line.id,
                box_code=line.box_code,
                label=line.label,
                amount=line.amount,
                sort_order=line.sort_order,
            )
            for line in sorted(tax_return.lines, key=lambda x: x.sort_order)
        )
        return TaxReturnDTO(
            id=tax_return.id,
            company_id=tax_return.company_id,
            obligation_id=getattr(tax_return, "obligation_id", 0) or 0,
            tax_type_code=tax_return.tax_type_code,
            period_start=tax_return.period_start,
            period_end=tax_return.period_end,
            status_code=tax_return.status_code,
            total_due_amount=tax_return.total_due_amount,
            total_paid_amount=tax_return.total_paid_amount,
            filed_at=tax_return.filed_at,
            otp_reference=getattr(tax_return, "otp_reference", None),
            external_reference=getattr(tax_return, "external_reference", None),
            notes=getattr(tax_return, "notes", None),
            prepared_by_user_id=getattr(tax_return, "prepared_by_user_id", None),
            lines=lines,
        )

    # ---------------- HTML rendering ----------------

    _STYLE = """
        body { font-family: 'Segoe UI', Arial, sans-serif; color: #1f2937;
               font-size: 10pt; margin: 22px; }
        .official-header { text-align: center; font-size: 9pt;
               color: #374151; margin-bottom: 14px; line-height: 1.4; }
        .official-header .country { font-weight: 700; letter-spacing: 1px;
               font-size: 10pt; color: #111827; }
        .official-header .motto { font-style: italic; color: #6b7280; }
        .official-header .ministry { margin-top: 4px; font-weight: 600; }
        .form-title { text-align: center; font-size: 13pt; font-weight: 700;
               margin: 8px 0 4px 0; color: #111827;
               border-top: 2px solid #111827; border-bottom: 2px solid #111827;
               padding: 6px 0; text-transform: uppercase; }
        .form-subtitle { text-align: center; color: #4b5563; font-size: 9pt;
               margin-bottom: 12px; }
        .identity { border: 1px solid #cbd5e1; padding: 8px 12px;
               margin-bottom: 12px; }
        .identity table { width: 100%; border-collapse: collapse; }
        .identity td { padding: 2px 6px; vertical-align: top; }
        .identity td.k { color: #6b7280; width: 130px; font-size: 9pt; }
        .identity td.v { color: #111827; font-weight: 600; }
        .regime-row { margin-top: 4px; font-size: 9pt; }
        .regime-row .checkbox { display: inline-block; width: 14px; height: 14px;
               border: 1.5px solid #4b5563; vertical-align: middle;
               margin: 0 4px 0 12px; text-align: center;
               line-height: 12px; font-weight: 700; color: #111827; }

        .section { margin-top: 14px; }
        .section h2 { font-size: 11pt; margin: 0 0 4px 0; color: #111827;
               background: #1f2937; color: #f9fafb;
               padding: 4px 10px; text-transform: uppercase;
               letter-spacing: 0.5px; font-weight: 600; }
        table.form { width: 100%; border-collapse: collapse;
               border: 1px solid #1f2937; }
        table.form th, table.form td { border: 1px solid #cbd5e1;
               padding: 4px 6px; font-size: 9.5pt; }
        table.form th { background: #f3f4f6; color: #374151; text-align: left;
               font-weight: 600; }
        table.form td.code { width: 50px; font-family: 'Consolas', monospace;
               text-align: center; color: #1e3a8a; font-weight: 600; }
        table.form td.label { color: #1f2937; }
        table.form td.amt, table.form th.amt { text-align: right;
               font-variant-numeric: tabular-nums;
               font-family: 'Consolas', monospace;
               width: 110px; }
        table.form td.rate { text-align: center; color: #4b5563; width: 60px; }
        table.form td.empty { color: #9ca3af; }
        table.form tr.emphasis td { background: #f9fafb; font-weight: 700;
               color: #111827; }

        .totals { margin-top: 14px; border-top: 2px solid #111827;
               padding-top: 8px; }
        .totals table { width: 100%; }
        .totals td { padding: 4px 6px; }
        .totals td.k { color: #4b5563; text-align: right; }
        .totals td.v { font-weight: 700; text-align: right; width: 140px;
               font-variant-numeric: tabular-nums;
               font-family: 'Consolas', monospace; color: #111827; }
        .totals td.due { color: #b91c1c; }

        .notes { margin-top: 12px; padding: 8px 12px; background: #f9fafb;
               border-left: 3px solid #d1d5db; font-size: 9pt; color: #374151; }
        .footer { margin-top: 24px; font-size: 8.5pt; color: #9ca3af;
               text-align: center; border-top: 1px dashed #e5e7eb; padding-top: 8px; }
        .stamp { display: inline-block; padding: 4px 12px; border-radius: 12px;
               font-size: 9pt; font-weight: 700; }
        .stamp.draft { background: #fef3c7; color: #92400e; }
        .stamp.filed { background: #dcfce7; color: #166534; }
        .stamp.other { background: #e5e7eb; color: #374151; }
        .certification { margin-top: 20px; border-top: 1px solid #cbd5e1;
               padding-top: 12px; font-size: 9pt; }
        .certification .statement { font-style: italic; color: #374151;
               margin-bottom: 14px; line-height: 1.5; }
        .certification table { width: 100%; border-collapse: collapse; }
        .certification td { padding: 4px 8px; font-size: 9pt; }
        .certification td.sig-label { color: #6b7280; width: 140px; vertical-align: bottom; }
        .certification td.sig-line { border-bottom: 1px solid #9ca3af;
               height: 30px; vertical-align: bottom; padding-bottom: 4px; }
    """

    def _render_html(
        self, company: dict[str, str | None], tax_return: TaxReturnDTO
    ) -> str:
        is_vat = tax_return.tax_type_code == TAX_TYPE_VAT
        layout = build_vat_form_layout(tax_return) if is_vat else None

        header = self._render_official_header()
        title = self._render_form_title(tax_return, layout)
        identity = self._render_identity_block(company, tax_return, layout)

        if is_vat and layout is not None:
            sections_html = "".join(
                self._render_section(s) for s in layout.sections
            )
            totals_html = self._render_totals(layout)
        else:
            sections_html = self._render_assessed_section(tax_return)
            totals_html = self._render_assessed_totals(tax_return)

        notes_html = ""
        if tax_return.notes:
            notes_html = (
                f'<div class="notes"><b>Notes:</b><br/>'
                f'{_esc(tax_return.notes).replace(chr(10), "<br/>")}'
                "</div>"
            )

        certification_html = self._render_certification_block(company)

        footer = (
            f'<div class="footer">Generated by Seeker Accounting \u00b7 '
            f'{datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}'
            f' \u00b7 Return #{tax_return.id}</div>'
        )

        return (
            f'<!DOCTYPE html><html><head><meta charset="utf-8"/>'
            f'<style>{self._STYLE}</style></head><body>'
            f'{header}{title}{identity}{sections_html}{totals_html}{notes_html}'
            f'{certification_html}{footer}'
            f'</body></html>'
        )

    # ── Header / title / identity ─────────────────────────────────────

    @staticmethod
    def _render_certification_block(company: dict[str, str | None]) -> str:
        """T46: legal certification statement + signature block."""
        taxpayer = _esc(company.get("name") or "")
        return (
            '<div class="certification">'
            '<div class="statement">'
            'Je certifie sinc\u00e8re et compl\u00e8te la pr\u00e9sente d\u00e9claration. / '
            'I certify the present declaration to be true and complete.'
            '</div>'
            '<table>'
            '<tr>'
            '<td class="sig-label">Nom / Name:</td>'
            f'<td class="sig-line">{taxpayer}</td>'
            '<td class="sig-label">Qualit\u00e9 / Capacity:</td>'
            '<td class="sig-line">&nbsp;</td>'
            '</tr>'
            '<tr>'
            '<td class="sig-label">Fait \u00e0 / Done at:</td>'
            '<td class="sig-line">&nbsp;</td>'
            '<td class="sig-label">Le / On:</td>'
            '<td class="sig-line">&nbsp;</td>'
            '</tr>'
            '<tr>'
            '<td class="sig-label">Signature et cachet / Signature and stamp:</td>'
            '<td class="sig-line" colspan="3">&nbsp;</td>'
            '</tr>'
            '</table>'
            '</div>'
        )

    @staticmethod
    def _render_official_header() -> str:
        return (
            '<div class="official-header">'
            '<div class="country">REPUBLIQUE DU CAMEROUN / REPUBLIC OF CAMEROON</div>'
            '<div class="motto">Paix \u2013 Travail \u2013 Patrie / Peace \u2013 Work \u2013 Fatherland</div>'
            '<div class="ministry">MINISTERE DES FINANCES \u2014 DIRECTION GENERALE DES IMPOTS</div>'
            '<div class="ministry">MINISTRY OF FINANCE \u2014 DIRECTORATE GENERAL OF TAXATION</div>'
            '</div>'
        )

    @staticmethod
    def _render_form_title(
        tax_return: TaxReturnDTO, layout: VATFormLayout | None
    ) -> str:
        if tax_return.tax_type_code == TAX_TYPE_VAT:
            sub = (
                "Return for Business and Liquor Licence, Income, Turnover "
                "and Specific Activities Taxes \u2014 VAT page"
            )
            title = "Tax Return \u2014 Value Added Tax (VAT)"
        else:
            sub = "Assessed-amount filing"
            title = f"Tax Return \u2014 {tax_return.tax_type_code}"
        return (
            f'<div class="form-title">{_esc(title)}</div>'
            f'<div class="form-subtitle">{_esc(sub)}</div>'
        )

    def _render_identity_block(
        self,
        company: dict[str, str | None],
        tax_return: TaxReturnDTO,
        layout: VATFormLayout | None,
    ) -> str:
        status_class = {
            "DRAFT": "draft",
            "FILED": "filed",
        }.get(tax_return.status_code, "other")

        period_label = (
            layout.period_label
            if layout is not None
            else (
                f"{tax_return.period_start.isoformat()} \u2014 "
                f"{tax_return.period_end.isoformat()}"
            )
        )
        month_label = layout.month_label if layout is not None else _DASH
        fiscal_year = (
            layout.fiscal_year
            if layout is not None and layout.fiscal_year
            else (
                tax_return.period_start.year
                if tax_return.period_start
                else _DASH
            )
        )

        # T46: dynamic regime checkboxes — tick whichever regime the company uses.
        regime_code = (company.get("tax_regime_code") or "").upper()
        _tick = "\u2713"
        actual_tick = _tick if regime_code in ("ACTUAL", "REEL", "") else "&nbsp;"
        simplified_tick = _tick if regime_code in ("SIMPLIFIED", "SIMPLIFIE", "SIMPLIFIÉ") else "&nbsp;"
        regime_row = (
            '<div class="regime-row">'
            'Assessment regime:'
            f'<span class="checkbox">{actual_tick}</span>Actual (R\u00e9el)'
            f'<span class="checkbox">{simplified_tick}</span>Simplified (Simplifi\u00e9)'
            '</div>'
        )

        tax_center = _esc(company.get("tax_center_code")) or _DASH
        segment = _esc(company.get("taxpayer_segment_code")) or _DASH

        return (
            '<div class="identity">'
            '<table>'
            f'<tr><td class="k">Tax-payer</td><td class="v">{_esc(company["name"])}</td>'
            f'<td class="k">UIN / NIU</td><td class="v">{_esc(company["tax_id"]) or _DASH}</td></tr>'
            f'<tr><td class="k">Legal name</td><td class="v">{_esc(company["legal_name"]) or _DASH}</td>'
            f'<td class="k">Registration #</td><td class="v">{_esc(company["registration_number"]) or _DASH}</td></tr>'
            f'<tr><td class="k">Address</td><td class="v">{_esc(company["address"]) or _DASH}</td>'
            f'<td class="k">Phone</td><td class="v">{_esc(company["phone"]) or _DASH}</td></tr>'
            f'<tr><td class="k">Email</td><td class="v">{_esc(company["email"]) or _DASH}</td>'
            f'<td class="k">Status</td><td class="v"><span class="stamp {status_class}">{_esc(tax_return.status_code)}</span></td></tr>'
            f'<tr><td class="k">Fiscal year</td><td class="v">{fiscal_year}</td>'
            f'<td class="k">Month / period</td><td class="v">{_esc(month_label)}</td></tr>'
            f'<tr><td class="k">Period</td><td class="v">{_esc(period_label)}</td>'
            f'<td class="k">Filed at</td><td class="v">'
            + (
                tax_return.filed_at.strftime("%Y-%m-%d %H:%M")
                if tax_return.filed_at
                else _DASH
            )
            + '</td></tr>'
            f'<tr><td class="k">OTP reference</td><td class="v">{_esc(tax_return.otp_reference) or _DASH}</td>'
            f'<td class="k">External ref.</td><td class="v">{_esc(tax_return.external_reference) or _DASH}</td></tr>'
            f'<tr><td class="k">Tax centre</td><td class="v">{tax_center}</td>'
            f'<td class="k">Taxpayer segment</td><td class="v">{segment}</td></tr>'
            '</table>'
            f'{regime_row}'
            '</div>'
        )

    # ── Section rendering ─────────────────────────────────────────────

    def _render_section(self, section: VATFormSection) -> str:
        # Build column-group (head + alignment depends on section).
        if section.number == "4":
            head = (
                '<thead><tr>'
                '<th class="code">Code</th>'
                '<th class="label">Description</th>'
                '<th class="amt">Base (HT)</th>'
                '<th class="rate">Rate</th>'
                '<th class="amt">Tax amount</th>'
                '</tr></thead>'
            )
            body_rows = "".join(
                self._render_section_4_row(r) for r in section.rows
            )
        elif section.number == "8":
            head = (
                '<thead><tr>'
                '<th class="code">Code</th>'
                '<th class="label">Description</th>'
                '<th class="amt">Principal</th>'
                '<th class="amt">Add. Council Tax</th>'
                '<th class="amt">Fines</th>'
                '<th class="amt">Total</th>'
                '</tr></thead>'
            )
            body_rows = "".join(
                self._render_section_8_row(r) for r in section.rows
            )
        else:
            head = (
                '<thead><tr>'
                '<th class="code">Code</th>'
                '<th class="label">Description</th>'
                '<th class="amt">Amount</th>'
                '</tr></thead>'
            )
            body_rows = "".join(
                self._render_section_simple_row(r) for r in section.rows
            )

        return (
            f'<div class="section">'
            f'<h2>Section {section.number} \u2014 {_esc(section.title)}</h2>'
            f'<table class="form">{head}<tbody>{body_rows}</tbody></table>'
            f'</div>'
        )

    @staticmethod
    def _render_section_4_row(row: VATFormRow) -> str:
        cls = "emphasis" if row.emphasis else ""
        return (
            f'<tr class="{cls}">'
            f'<td class="code">{_esc(row.code)}</td>'
            f'<td class="label">{_esc(row.label)}</td>'
            f'<td class="amt">{_fmt_amount(row.base)}</td>'
            f'<td class="rate">{_esc(row.rate) or _DASH}</td>'
            f'<td class="amt">{_fmt_amount(row.amount)}</td>'
            f'</tr>'
        )

    @staticmethod
    def _render_section_8_row(row: VATFormRow) -> str:
        cls = "emphasis" if row.emphasis else ""
        return (
            f'<tr class="{cls}">'
            f'<td class="code">{_esc(row.code)}</td>'
            f'<td class="label">{_esc(row.label)}</td>'
            f'<td class="amt">{_fmt_amount(row.amount)}</td>'
            f'<td class="amt empty">{_DASH}</td>'
            f'<td class="amt empty">{_DASH}</td>'
            f'<td class="amt">{_fmt_amount(row.amount)}</td>'
            f'</tr>'
        )

    @staticmethod
    def _render_section_simple_row(row: VATFormRow) -> str:
        cls = "emphasis" if row.emphasis else ""
        return (
            f'<tr class="{cls}">'
            f'<td class="code">{_esc(row.code)}</td>'
            f'<td class="label">{_esc(row.label)}</td>'
            f'<td class="amt">{_fmt_amount(row.amount)}</td>'
            f'</tr>'
        )

    # ── Totals (VAT) ──────────────────────────────────────────────────

    @staticmethod
    def _render_totals(layout: VATFormLayout) -> str:
        outstanding_class = "due" if layout.outstanding > 0 else ""
        return (
            f'<div class="totals">'
            f'<table>'
            f'<tr><td class="k">Total due</td><td class="v">{_fmt_amount(layout.total_due)}</td></tr>'
            f'<tr><td class="k">Total paid</td><td class="v">{_fmt_amount(layout.total_paid)}</td></tr>'
            f'<tr><td class="k">Outstanding</td>'
            f'<td class="v {outstanding_class}">{_fmt_amount(layout.outstanding)}</td></tr>'
            f'</table></div>'
        )

    # ── Non-VAT (assessed) ────────────────────────────────────────────

    @staticmethod
    def _render_assessed_section(tax_return: TaxReturnDTO) -> str:
        return (
            '<div class="section">'
            f'<h2>Assessed Amount \u2014 {_esc(tax_return.tax_type_code)}</h2>'
            '<table class="form">'
            '<thead><tr>'
            '<th class="label">Description</th>'
            '<th class="amt">Amount</th>'
            '</tr></thead>'
            '<tbody>'
            f'<tr class="emphasis">'
            f'<td class="label">Assessed liability for the period</td>'
            f'<td class="amt">{_fmt_amount(tax_return.total_due_amount)}</td>'
            f'</tr>'
            '</tbody></table>'
            '</div>'
        )

    @staticmethod
    def _render_assessed_totals(tax_return: TaxReturnDTO) -> str:
        outstanding = Decimal(tax_return.total_due_amount or 0) - Decimal(
            tax_return.total_paid_amount or 0
        )
        outstanding_class = "due" if outstanding > 0 else ""
        return (
            f'<div class="totals"><table>'
            f'<tr><td class="k">Total due</td><td class="v">{_fmt_amount(tax_return.total_due_amount)}</td></tr>'
            f'<tr><td class="k">Total paid</td><td class="v">{_fmt_amount(tax_return.total_paid_amount)}</td></tr>'
            f'<tr><td class="k">Outstanding</td><td class="v {outstanding_class}">{_fmt_amount(outstanding)}</td></tr>'
            f'</table></div>'
        )

    # ---------------- Audit ----------------

    def _record_audit(
        self, company_id: int, return_id: int, output_path: str
    ) -> None:
        if self._audit_service is None:
            return
        try:
            from seeker_accounting.modules.audit.event_type_catalog import (
                MODULE_TAXATION,
            )
            from seeker_accounting.modules.audit.dto.audit_event_dto import (
                RecordAuditEventCommand,
            )

            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    module_code=MODULE_TAXATION,
                    event_type_code="TAX_RETURN_EXPORTED_PDF",
                    entity_type="tax_return",
                    entity_id=return_id,
                    description=(
                        f"Exported tax return #{return_id} to PDF: {output_path}"
                    ),
                ),
            )
        except Exception:  # noqa: BLE001 \u2014 audit must never break export
            return
