"""Print and export service for Audit Log.

Handles all three output formats (PDF, Word, Excel) for the audit event listing.
List-only — no single-document detail view.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from seeker_accounting.modules.audit.dto.audit_event_dto import AuditEventDTO
from seeker_accounting.modules.companies.dto.company_dto import CompanyDetailDTO
from seeker_accounting.platform.printing.html_builder import (
    build_company_header,
    build_data_table,
    build_document_title_block,
    wrap_html,
)
from seeker_accounting.platform.printing.print_data_protocol import (
    CompanyHeaderData,
    PageSize,
    PrintExportResult,
    PrintFormat,
)

if TYPE_CHECKING:
    from seeker_accounting.modules.companies.services.company_logo_service import CompanyLogoService
    from seeker_accounting.modules.companies.services.company_service import CompanyService
    from seeker_accounting.platform.printing.excel_builder import ExcelWorkbookBuilder
    from seeker_accounting.platform.printing.print_engine import PrintEngine
    from seeker_accounting.platform.printing.word_builder import WordDocumentBuilder


class AuditLogPrintService:
    """Renders the audit event log to PDF, Word, or Excel."""

    def __init__(
        self,
        print_engine: "PrintEngine",
        company_service: "CompanyService",
        company_logo_service: "CompanyLogoService",
    ) -> None:
        self._engine = print_engine
        self._company_service = company_service
        self._logo_service = company_logo_service

    # ── Public API ──────────────────────────────────────────────────────────────

    def print_event_list(
        self,
        company_id: int,
        events: list[AuditEventDTO],
        result: PrintExportResult,
    ) -> None:
        """Render the audit log to the chosen format and path."""
        company = self._company_service.get_company(company_id)
        header = self._make_company_header(company)

        if result.format == PrintFormat.PDF:
            html = self._list_html(header, events, result.page_size)
            self._engine.render_pdf(
                html, result.output_path,
                page_size=result.page_size,
                orientation=result.orientation,
            )
        elif result.format == PrintFormat.WORD:
            doc = self._list_word(header, events, result.page_size, result.orientation)
            doc.save(result.output_path)
        else:
            wb = self._list_excel(header, events, result.page_size, result.orientation)
            wb.save(result.output_path)

    # ── Company header ──────────────────────────────────────────────────────────

    def _make_company_header(self, company: CompanyDetailDTO) -> CompanyHeaderData:
        logo_path: str | None = None
        if company.logo_storage_path:
            resolved = self._logo_service.resolve_logo_path(company.logo_storage_path)
            if resolved:
                logo_path = str(resolved)
        return CompanyHeaderData(
            name=company.display_name,
            legal_name=(
                company.legal_name
                if company.legal_name and company.legal_name != company.display_name
                else None
            ),
            address_line_1=company.address_line_1,
            address_line_2=company.address_line_2,
            city=company.city,
            region=company.region,
            country=company.country_code,
            phone=company.phone,
            email=company.email,
            tax_identifier=company.tax_identifier,
            registration_number=company.registration_number,
            logo_path=logo_path,
        )

    # ── Formatting helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _fmt_ts(ts: datetime | None) -> str:
        return ts.strftime("%d/%m/%Y %H:%M:%S") if ts else "—"

    @staticmethod
    def _entity_label(e: AuditEventDTO) -> str:
        if e.entity_id is not None:
            return f"{e.entity_type} #{e.entity_id}"
        return e.entity_type

    # ── HTML builder ────────────────────────────────────────────────────────────

    def _list_html(
        self,
        company: CompanyHeaderData,
        events: list[AuditEventDTO],
        page_size: PageSize,
    ) -> str:
        parts: list[str] = [
            build_company_header(company),
            build_document_title_block(
                "Audit Log",
                subtitle=f"{len(events)} event(s)",
            ),
        ]
        cols = ["Timestamp", "Module", "Event Type", "Entity", "Actor", "Description"]
        rows = [
            [
                self._fmt_ts(e.created_at),
                e.module_code.replace("_", " ").title(),
                e.event_type_code.replace("_", " ").title(),
                self._entity_label(e),
                e.actor_display_name or "System",
                e.description,
            ]
            for e in events
        ]
        total_row = [f"{len(events)} events", "", "", "", "", ""]
        parts.append(build_data_table(
            cols,
            rows,
            total_row=total_row,
            nowrap_columns={0},
            column_widths={
                0: "16%",
                1: "12%",
                2: "14%",
                3: "14%",
                4: "14%",
                5: "30%",
            },
        ))
        return wrap_html("".join(parts), page_size=page_size)

    # ── Word builder ────────────────────────────────────────────────────────────

    def _list_word(
        self,
        company: CompanyHeaderData,
        events: list[AuditEventDTO],
        page_size: PageSize,
        orientation,
    ) -> "WordDocumentBuilder":
        from seeker_accounting.platform.printing.word_builder import WordDocumentBuilder

        doc = WordDocumentBuilder(page_size=page_size, orientation=orientation)
        doc.add_company_header(company)
        doc.add_document_title("Audit Log", subtitle=f"{len(events)} event(s)")
        cols = ["Timestamp", "Module", "Event Type", "Entity", "Actor", "Description"]
        rows = [
            [
                self._fmt_ts(e.created_at),
                e.module_code.replace("_", " ").title(),
                e.event_type_code.replace("_", " ").title(),
                self._entity_label(e),
                e.actor_display_name or "System",
                e.description,
            ]
            for e in events
        ]
        doc.add_data_table(
            cols, rows,
            total_row=[f"{len(events)} events", "", "", "", "", ""],
        )
        return doc

    # ── Excel builder ───────────────────────────────────────────────────────────

    def _list_excel(
        self,
        company: CompanyHeaderData,
        events: list[AuditEventDTO],
        page_size: PageSize,
        orientation,
    ) -> "ExcelWorkbookBuilder":
        from seeker_accounting.platform.printing.excel_builder import ExcelWorkbookBuilder

        wb = ExcelWorkbookBuilder(page_size=page_size, orientation=orientation)
        sh = wb.add_sheet("Audit Log")
        sh.write_document_header(company, "Audit Log")
        sh.write_blank_row()
        sh.write_table_header(["Timestamp", "Module", "Event Type", "Entity", "Actor", "Description"])
        for e in events:
            sh.write_table_row([
                self._fmt_ts(e.created_at),
                e.module_code.replace("_", " ").title(),
                e.event_type_code.replace("_", " ").title(),
                self._entity_label(e),
                e.actor_display_name or "System",
                e.description,
            ])
        sh.write_totals_row([f"{len(events)} events", "", "", "", "", ""])
        sh.write_branded_footer()
        sh.set_column_widths({1: 20, 2: 16, 3: 18, 4: 20, 5: 18, 6: 40})
        return wb
