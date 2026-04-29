"""Tax return PDF export service (T24).

Renders a posted tax return (header + breakdown lines + totals) into
a single-page printable PDF using the existing Qt-based print engine
(no external PDF library required).
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
from seeker_accounting.modules.taxation.dto.tax_compliance_dto import (
    ExportTaxReturnPDFCommand,
    ExportTaxReturnPDFResultDTO,
)
from seeker_accounting.modules.taxation.repositories.tax_return_repository import (
    TaxReturnRepository,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService
    from seeker_accounting.platform.printing.print_engine import PrintEngine


TaxReturnRepositoryFactory = Callable[[Session], TaxReturnRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]


def _fmt_amount(value: Decimal | None) -> str:
    if value is None:
        return "0.00"
    quantized = Decimal(value).quantize(Decimal("0.01"))
    # Use thousand separators with non-breaking space friendly comma.
    return f"{quantized:,.2f}"


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
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._app_context = app_context
        self._tax_return_repository_factory = tax_return_repository_factory
        self._company_repository_factory = company_repository_factory
        self._permission_service = permission_service
        self._print_engine = print_engine
        self._audit_service = audit_service

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

            # Snapshot all data we need before closing the session
            html = self._render_html(company, tax_return)

        self._print_engine.render_pdf(html, output_path)
        self._record_audit(company_id, command.return_id, output_path)

        return ExportTaxReturnPDFResultDTO(
            return_id=command.return_id,
            output_path=output_path,
            rendered_at=datetime.utcnow(),
        )

    # ---------------- Helpers ----------------

    def _render_html(self, company, tax_return) -> str:
        company_name = escape(
            getattr(company, "display_name", None)
            or getattr(company, "legal_name", "")
            or ""
        )
        tax_id = escape(getattr(company, "tax_identifier", None) or "—")

        rows_html: list[str] = []
        for line in sorted(tax_return.lines, key=lambda x: x.sort_order):
            rows_html.append(
                "<tr>"
                f"<td class='code'>{escape(line.box_code)}</td>"
                f"<td>{escape(line.label)}</td>"
                f"<td class='amt'>{_fmt_amount(line.amount)}</td>"
                "</tr>"
            )
        if not rows_html:
            rows_html.append(
                "<tr><td colspan='3' class='empty'>No breakdown lines on this return.</td></tr>"
            )

        period = (
            f"{tax_return.period_start.isoformat()} — "
            f"{tax_return.period_end.isoformat()}"
        )
        filed_at = (
            tax_return.filed_at.strftime("%Y-%m-%d %H:%M")
            if tax_return.filed_at
            else "—"
        )
        otp_ref = escape(tax_return.otp_reference or "—")
        ext_ref = escape(tax_return.external_reference or "—")
        notes = escape(tax_return.notes or "").replace("\n", "<br/>")

        return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/>
<style>
  body {{ font-family: Arial, sans-serif; color: #1f2937; font-size: 11pt; margin: 24px; }}
  h1 {{ font-size: 18pt; margin: 0 0 4px 0; color: #111827; }}
  h2 {{ font-size: 12pt; margin: 16px 0 6px 0; color: #374151; border-bottom: 1px solid #e5e7eb; padding-bottom: 2px; }}
  table.meta td {{ padding: 2px 8px 2px 0; }}
  table.meta td.k {{ color: #6b7280; }}
  table.lines {{ width: 100%; border-collapse: collapse; margin-top: 6px; }}
  table.lines th, table.lines td {{ border-bottom: 1px solid #e5e7eb; padding: 4px 6px; }}
  table.lines th {{ text-align: left; background: #f9fafb; font-size: 10pt; }}
  table.lines td.code {{ width: 80px; font-family: 'Consolas', monospace; }}
  table.lines td.amt, table.lines th.amt {{ text-align: right; width: 140px; font-variant-numeric: tabular-nums; }}
  table.lines td.empty {{ text-align: center; color: #9ca3af; font-style: italic; padding: 12px; }}
  table.totals {{ margin-top: 12px; width: 100%; }}
  table.totals td {{ padding: 4px 6px; }}
  table.totals td.label {{ text-align: right; color: #374151; }}
  table.totals td.amt {{ text-align: right; font-weight: bold; width: 160px; font-variant-numeric: tabular-nums; }}
  .notes {{ margin-top: 12px; padding: 8px; background: #f9fafb; border-left: 3px solid #d1d5db; font-size: 10pt; }}
  .footer {{ margin-top: 24px; font-size: 9pt; color: #9ca3af; text-align: center; }}
</style></head>
<body>
  <h1>{company_name}</h1>
  <div style="color:#6b7280; font-size:10pt;">Tax ID (NIU): {tax_id}</div>
  <h2>Tax Return — {escape(tax_return.tax_type_code)}</h2>
  <table class="meta">
    <tr><td class="k">Return ID</td><td>#{tax_return.id}</td>
        <td class="k">Status</td><td>{escape(tax_return.status_code)}</td></tr>
    <tr><td class="k">Period</td><td>{period}</td>
        <td class="k">Filed</td><td>{filed_at}</td></tr>
    <tr><td class="k">OTP Reference</td><td>{otp_ref}</td>
        <td class="k">External Reference</td><td>{ext_ref}</td></tr>
  </table>
  <h2>Breakdown</h2>
  <table class="lines">
    <thead><tr><th>Box</th><th>Label</th><th class="amt">Amount</th></tr></thead>
    <tbody>{''.join(rows_html)}</tbody>
  </table>
  <table class="totals">
    <tr><td class="label">Total due</td><td class="amt">{_fmt_amount(tax_return.total_due_amount)}</td></tr>
    <tr><td class="label">Total paid</td><td class="amt">{_fmt_amount(tax_return.total_paid_amount)}</td></tr>
    <tr><td class="label">Outstanding</td><td class="amt">{_fmt_amount(Decimal(tax_return.total_due_amount) - Decimal(tax_return.total_paid_amount))}</td></tr>
  </table>
  {f'<div class="notes"><b>Notes:</b><br/>{notes}</div>' if notes else ''}
  <div class="footer">Generated by Seeker Accounting · {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</div>
</body></html>"""

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
        except Exception:  # noqa: BLE001 — audit must never break export
            return
