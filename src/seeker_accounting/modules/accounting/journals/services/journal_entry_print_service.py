"""Print and export service for Journal Entries and Journal Register.

Handles all three output formats (PDF, Word, Excel) for:
  - Single journal entry detail document
  - Journal entry register list
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from seeker_accounting.modules.companies.dto.company_dto import CompanyDetailDTO
from seeker_accounting.modules.accounting.journals.dto.journal_dto import (
    JournalEntryDetailDTO,
    JournalEntryListItemDTO,
)
from seeker_accounting.platform.printing.html_builder import (
    build_company_header,
    build_data_table,
    build_document_title_block,
    build_key_value_grid,
    build_section_title,
    build_summary_box,
    fmt_decimal,
    h,
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
    from seeker_accounting.modules.accounting.journals.services.journal_service import JournalService
    from seeker_accounting.platform.printing.excel_builder import ExcelWorkbookBuilder
    from seeker_accounting.platform.printing.print_engine import PrintEngine
    from seeker_accounting.platform.printing.word_builder import WordDocumentBuilder


class JournalEntryPrintService:
    """Renders journal entry documents to PDF, Word, or Excel."""

    def __init__(
        self,
        print_engine: "PrintEngine",
        journal_service: "JournalService",
        company_service: "CompanyService",
        company_logo_service: "CompanyLogoService",
    ) -> None:
        self._engine = print_engine
        self._journal_service = journal_service
        self._company_service = company_service
        self._logo_service = company_logo_service

    # ── Public API ──────────────────────────────────────────────────────────────

    def print_journal_entry(
        self,
        company_id: int,
        journal_entry_id: int,
        result: PrintExportResult,
    ) -> None:
        """Render a single journal entry to the chosen format and path."""
        entry = self._journal_service.get_journal_entry(company_id, journal_entry_id)
        company = self._company_service.get_company(company_id)
        header = self._make_company_header(company)

        if result.format == PrintFormat.PDF:
            html = self._entry_html(header, entry, result.page_size)
            self._engine.render_pdf(
                html, result.output_path,
                page_size=result.page_size,
                orientation=result.orientation,
            )
        elif result.format == PrintFormat.WORD:
            doc = self._entry_word(header, entry, result.page_size, result.orientation)
            doc.save(result.output_path)
        else:
            wb = self._entry_excel(header, entry, result.page_size, result.orientation)
            wb.save(result.output_path)

    def print_journal_list(
        self,
        company_id: int,
        entries: list[JournalEntryListItemDTO],
        result: PrintExportResult,
    ) -> None:
        """Render the journal register (list) to the chosen format and path."""
        company = self._company_service.get_company(company_id)
        header = self._make_company_header(company)

        if result.format == PrintFormat.PDF:
            html = self._entry_list_html(header, entries, result.page_size)
            self._engine.render_pdf(
                html, result.output_path,
                page_size=result.page_size,
                orientation=result.orientation,
            )
        elif result.format == PrintFormat.WORD:
            doc = self._entry_list_word(header, entries, result.page_size, result.orientation)
            doc.save(result.output_path)
        else:
            wb = self._entry_list_excel(header, entries, result.page_size, result.orientation)
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
    def _fmt_date(d: date | None) -> str:
        return d.strftime("%d/%m/%Y") if d else "—"

    @staticmethod
    def _fmt_amount(v: Decimal | None) -> str:
        return fmt_decimal(v) if v is not None else "—"

    # ── HTML builders ───────────────────────────────────────────────────────────

    def _entry_html(
        self,
        company: CompanyHeaderData,
        entry: JournalEntryDetailDTO,
        page_size: PageSize,
    ) -> str:
        subtitle = entry.entry_number or f"Draft #{entry.id}"
        parts: list[str] = [
            build_company_header(company),
            build_document_title_block("Journal Entry", subtitle=subtitle),
            build_key_value_grid([
                ("Entry #", entry.entry_number or "—"),
                ("Entry Date", self._fmt_date(entry.entry_date)),
                ("Transaction Date", self._fmt_date(entry.transaction_date)),
                ("Fiscal Period", entry.fiscal_period_code),
                ("Journal Type", entry.journal_type_code),
                ("Reference", entry.reference_text or "—"),
                ("Status", entry.status_code.title()),
                ("Source Module", entry.source_module_code or "—"),
            ]),
        ]

        if entry.description:
            parts.append(
                f'<p style="font-size:9pt;color:#444;margin:6px 0 10px 0;font-style:italic;">{h(entry.description)}</p>'
            )

        parts.append(build_section_title("Journal Lines"))
        line_cols = ["#", "Account Code", "Account Name", "Description", "Debit", "Credit"]
        line_rows = [
            [
                str(ln.line_number),
                ln.account_code,
                ln.account_name,
                ln.line_description or "",
                self._fmt_amount(ln.debit_amount) if ln.debit_amount else "",
                self._fmt_amount(ln.credit_amount) if ln.credit_amount else "",
            ]
            for ln in entry.lines
        ]
        total_row = [
            "", "", "", "TOTALS",
            self._fmt_amount(entry.totals.total_debit),
            self._fmt_amount(entry.totals.total_credit),
        ]
        parts.append(build_data_table(
            line_cols, line_rows,
            numeric_columns={4, 5},
            total_row=total_row,
        ))

        balance_label = "Balanced" if entry.totals.is_balanced else f"Imbalance: {self._fmt_amount(entry.totals.imbalance_amount)}"
        summary = build_summary_box([
            ("Total Debit", self._fmt_amount(entry.totals.total_debit)),
            ("Total Credit", self._fmt_amount(entry.totals.total_credit)),
            ("Status", balance_label),
        ], highlight_last=False)
        parts.append(
            '<table style="width:100%;"><tr>'
            '<td style="vertical-align:top;width:50%;"></td>'
            f'<td style="vertical-align:top;width:50%;">{summary}</td>'
            '</tr></table>'
        )

        return wrap_html("".join(parts), page_size=page_size)

    def _entry_list_html(
        self,
        company: CompanyHeaderData,
        entries: list[JournalEntryListItemDTO],
        page_size: PageSize,
    ) -> str:
        parts: list[str] = [
            build_company_header(company),
            build_document_title_block(
                "Journal Entry Register",
                subtitle=f"{len(entries)} entr{'y' if len(entries) == 1 else 'ies'}",
            ),
        ]
        cols = [
            "Entry #", "Date", "Period", "Type", "Reference",
            "Description", "Debit", "Credit", "Bal.", "Status",
        ]
        rows = [
            [
                e.entry_number or f"#{e.id}",
                self._fmt_date(e.entry_date),
                e.fiscal_period_code,
                e.journal_type_code,
                e.reference_text or "",
                (e.description or "")[:40],
                self._fmt_amount(e.total_debit),
                self._fmt_amount(e.total_credit),
                "Y" if e.is_balanced else "N",
                e.status_code.title(),
            ]
            for e in entries
        ]
        total_debit = sum(e.total_debit for e in entries)
        total_credit = sum(e.total_credit for e in entries)
        total_row = [
            "TOTALS", "", "", "", "", f"{len(entries)} entries",
            fmt_decimal(total_debit),
            fmt_decimal(total_credit),
            "", "",
        ]
        parts.append(build_data_table(
            cols, rows,
            numeric_columns={6, 7},
            total_row=total_row,
            nowrap_columns={0, 1, 2, 3, 8, 9},
            column_widths={
                0: "11%",
                1: "8%",
                2: "10%",
                3: "10%",
                4: "15%",
                5: "18%",
                6: "10%",
                7: "10%",
                8: "3%",
                9: "5%",
            },
        ))
        return wrap_html("".join(parts), page_size=page_size)

    # ── Word builders ───────────────────────────────────────────────────────────

    def _entry_word(
        self,
        company: CompanyHeaderData,
        entry: JournalEntryDetailDTO,
        page_size: PageSize,
        orientation,
    ) -> "WordDocumentBuilder":
        from seeker_accounting.platform.printing.word_builder import WordDocumentBuilder

        subtitle = entry.entry_number or f"Draft #{entry.id}"
        doc = WordDocumentBuilder(page_size=page_size, orientation=orientation)
        doc.add_company_header(company)
        doc.add_document_title("Journal Entry", subtitle=subtitle)
        doc.add_key_value_grid([
            ("Entry #", entry.entry_number or "—"),
            ("Entry Date", self._fmt_date(entry.entry_date)),
            ("Transaction Date", self._fmt_date(entry.transaction_date)),
            ("Fiscal Period", entry.fiscal_period_code),
            ("Journal Type", entry.journal_type_code),
            ("Reference", entry.reference_text or "—"),
            ("Status", entry.status_code.title()),
            ("Source Module", entry.source_module_code or "—"),
        ])
        if entry.description:
            doc.add_paragraph(entry.description, italic=True)

        doc.add_section_title("Journal Lines")
        line_cols = ["#", "Account Code", "Account Name", "Description", "Debit", "Credit"]
        line_rows = [
            [
                str(ln.line_number),
                ln.account_code,
                ln.account_name,
                ln.line_description or "",
                self._fmt_amount(ln.debit_amount) if ln.debit_amount else "",
                self._fmt_amount(ln.credit_amount) if ln.credit_amount else "",
            ]
            for ln in entry.lines
        ]
        doc.add_data_table(
            line_cols, line_rows,
            numeric_columns={4, 5},
            total_row=[
                "", "", "", "TOTALS",
                self._fmt_amount(entry.totals.total_debit),
                self._fmt_amount(entry.totals.total_credit),
            ],
        )

        balance_label = "Balanced" if entry.totals.is_balanced else f"Imbalance: {self._fmt_amount(entry.totals.imbalance_amount)}"
        doc.add_summary_pairs([
            ("Total Debit", self._fmt_amount(entry.totals.total_debit)),
            ("Total Credit", self._fmt_amount(entry.totals.total_credit)),
            ("Status", balance_label),
        ])
        return doc

    def _entry_list_word(
        self,
        company: CompanyHeaderData,
        entries: list[JournalEntryListItemDTO],
        page_size: PageSize,
        orientation,
    ) -> "WordDocumentBuilder":
        from seeker_accounting.platform.printing.word_builder import WordDocumentBuilder

        doc = WordDocumentBuilder(page_size=page_size, orientation=orientation)
        doc.add_company_header(company)
        doc.add_document_title("Journal Entry Register", subtitle=f"{len(entries)} entries")
        cols = [
            "Entry #", "Date", "Period", "Type", "Reference",
            "Debit", "Credit", "Bal.", "Status",
        ]
        rows = [
            [
                e.entry_number or f"#{e.id}",
                self._fmt_date(e.entry_date),
                e.fiscal_period_code,
                e.journal_type_code,
                e.reference_text or "",
                self._fmt_amount(e.total_debit),
                self._fmt_amount(e.total_credit),
                "Y" if e.is_balanced else "N",
                e.status_code.title(),
            ]
            for e in entries
        ]
        doc.add_data_table(
            cols, rows,
            numeric_columns={5, 6},
            total_row=[
                "TOTALS", "", "", "", "",
                fmt_decimal(sum(e.total_debit for e in entries)),
                fmt_decimal(sum(e.total_credit for e in entries)),
                "", "",
            ],
        )
        return doc

    # ── Excel builders ──────────────────────────────────────────────────────────

    def _entry_excel(
        self,
        company: CompanyHeaderData,
        entry: JournalEntryDetailDTO,
        page_size: PageSize,
        orientation,
    ) -> "ExcelWorkbookBuilder":
        from seeker_accounting.platform.printing.excel_builder import ExcelWorkbookBuilder

        subtitle = entry.entry_number or f"Draft #{entry.id}"
        wb = ExcelWorkbookBuilder(page_size=page_size, orientation=orientation)
        sh = wb.add_sheet("Journal Entry")
        sh.write_document_header(company, f"Journal Entry — {subtitle}")
        sh.write_key_value_pairs([
            ("Entry Date", self._fmt_date(entry.entry_date)),
            ("Fiscal Period", entry.fiscal_period_code),
            ("Journal Type", entry.journal_type_code),
            ("Reference", entry.reference_text or "—"),
            ("Status", entry.status_code.title()),
            ("Description", entry.description or "—"),
        ])
        sh.write_blank_row()
        sh.write_table_header(["#", "Account Code", "Account Name", "Description", "Debit", "Credit"])
        for ln in entry.lines:
            sh.write_table_row([
                ln.line_number,
                ln.account_code,
                ln.account_name,
                ln.line_description or "",
                ln.debit_amount if ln.debit_amount else "",
                ln.credit_amount if ln.credit_amount else "",
            ], numeric_columns={4, 5})
        sh.write_totals_row(["", "", "", "TOTALS", entry.totals.total_debit, entry.totals.total_credit])
        sh.write_branded_footer()
        return wb

    def _entry_list_excel(
        self,
        company: CompanyHeaderData,
        entries: list[JournalEntryListItemDTO],
        page_size: PageSize,
        orientation,
    ) -> "ExcelWorkbookBuilder":
        from seeker_accounting.platform.printing.excel_builder import ExcelWorkbookBuilder

        wb = ExcelWorkbookBuilder(page_size=page_size, orientation=orientation)
        sh = wb.add_sheet("Journal Register")
        sh.write_document_header(company, "Journal Entry Register")
        sh.write_blank_row()
        sh.write_table_header([
            "Entry #", "Date", "Period", "Type", "Reference",
            "Description", "Debit", "Credit", "Balanced", "Status",
        ])
        for e in entries:
            sh.write_table_row([
                e.entry_number or f"#{e.id}",
                self._fmt_date(e.entry_date),
                e.fiscal_period_code,
                e.journal_type_code,
                e.reference_text or "",
                (e.description or "")[:60],
                e.total_debit,
                e.total_credit,
                "Yes" if e.is_balanced else "No",
                e.status_code.title(),
            ], numeric_columns={6, 7})
        sh.write_totals_row([
            "TOTALS", "", "", "", "", f"{len(entries)} entries",
            sum(e.total_debit for e in entries),
            sum(e.total_credit for e in entries),
            "", "",
        ])
        sh.write_branded_footer()
        return wb
