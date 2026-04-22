"""Print and export service for Treasury Transfers and Transfer Register.

Handles all three output formats (PDF, Word, Excel) for:
  - Single treasury transfer detail document
  - Treasury transfer register list
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from seeker_accounting.modules.companies.dto.company_dto import CompanyDetailDTO
from seeker_accounting.modules.treasury.dto.treasury_transfer_dto import (
    TreasuryTransferDetailDTO,
    TreasuryTransferListItemDTO,
)
from seeker_accounting.platform.printing.html_builder import (
    build_company_header,
    build_data_table,
    build_document_title_block,
    build_key_value_grid,
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
    from seeker_accounting.modules.treasury.services.treasury_transfer_service import TreasuryTransferService
    from seeker_accounting.platform.printing.excel_builder import ExcelWorkbookBuilder
    from seeker_accounting.platform.printing.print_engine import PrintEngine
    from seeker_accounting.platform.printing.word_builder import WordDocumentBuilder


class TreasuryTransferPrintService:
    """Renders treasury transfer documents to PDF, Word, or Excel."""

    def __init__(
        self,
        print_engine: "PrintEngine",
        treasury_transfer_service: "TreasuryTransferService",
        company_service: "CompanyService",
        company_logo_service: "CompanyLogoService",
    ) -> None:
        self._engine = print_engine
        self._xfr_service = treasury_transfer_service
        self._company_service = company_service
        self._logo_service = company_logo_service

    # ── Public API ──────────────────────────────────────────────────────────────

    def print_transfer(
        self,
        company_id: int,
        transfer_id: int,
        result: PrintExportResult,
    ) -> None:
        """Render a single treasury transfer to the chosen format and path."""
        xfr = self._xfr_service.get_treasury_transfer(company_id, transfer_id)
        company = self._company_service.get_company(company_id)
        header = self._make_company_header(company)

        if result.format == PrintFormat.PDF:
            html = self._detail_html(header, xfr, result.page_size)
            self._engine.render_pdf(
                html, result.output_path,
                page_size=result.page_size,
                orientation=result.orientation,
            )
        elif result.format == PrintFormat.WORD:
            doc = self._detail_word(header, xfr, result.page_size, result.orientation)
            doc.save(result.output_path)
        else:
            wb = self._detail_excel(header, xfr, result.page_size, result.orientation)
            wb.save(result.output_path)

    def print_transfer_list(
        self,
        company_id: int,
        transfers: list[TreasuryTransferListItemDTO],
        result: PrintExportResult,
    ) -> None:
        """Render the transfer register (list) to the chosen format and path."""
        company = self._company_service.get_company(company_id)
        header = self._make_company_header(company)

        if result.format == PrintFormat.PDF:
            html = self._list_html(header, transfers, result.page_size)
            self._engine.render_pdf(
                html, result.output_path,
                page_size=result.page_size,
                orientation=result.orientation,
            )
        elif result.format == PrintFormat.WORD:
            doc = self._list_word(header, transfers, result.page_size, result.orientation)
            doc.save(result.output_path)
        else:
            wb = self._list_excel(header, transfers, result.page_size, result.orientation)
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

    # ── Detail HTML ─────────────────────────────────────────────────────────────

    def _detail_html(
        self,
        company: CompanyHeaderData,
        xfr: TreasuryTransferDetailDTO,
        page_size: PageSize,
    ) -> str:
        parts: list[str] = [
            build_company_header(company),
            build_document_title_block("Treasury Transfer", subtitle=xfr.transfer_number),
            build_key_value_grid([
                ("Transfer #", xfr.transfer_number),
                ("From Account", xfr.from_account_name),
                ("To Account", xfr.to_account_name),
                ("Date", self._fmt_date(xfr.transfer_date)),
                ("Currency", xfr.currency_code),
                ("Exchange Rate", str(xfr.exchange_rate) if xfr.exchange_rate else "—"),
                ("Amount", self._fmt_amount(xfr.amount)),
                ("Reference", xfr.reference_number or "—"),
                ("Status", xfr.status_code.title()),
            ]),
        ]

        summary = build_summary_box([
            ("Transfer Amount", self._fmt_amount(xfr.amount)),
        ], highlight_last=False)
        parts.append(
            '<table style="width:100%;"><tr>'
            '<td style="vertical-align:top;width:50%;"></td>'
            f'<td style="vertical-align:top;width:50%;">{summary}</td>'
            '</tr></table>'
        )

        if xfr.description:
            from seeker_accounting.platform.printing.html_builder import build_section_title
            parts.append(build_section_title("Description"))
            parts.append(
                f'<p style="font-size:9pt;color:#444;margin:4px 0;">{h(xfr.description)}</p>'
            )
        if xfr.notes:
            from seeker_accounting.platform.printing.html_builder import build_section_title
            parts.append(build_section_title("Notes"))
            parts.append(
                f'<p style="font-size:9pt;color:#444;margin:4px 0;">{h(xfr.notes)}</p>'
            )

        return wrap_html("".join(parts), page_size=page_size)

    # ── Detail Word ─────────────────────────────────────────────────────────────

    def _detail_word(
        self,
        company: CompanyHeaderData,
        xfr: TreasuryTransferDetailDTO,
        page_size: PageSize,
        orientation,
    ) -> "WordDocumentBuilder":
        from seeker_accounting.platform.printing.word_builder import WordDocumentBuilder

        doc = WordDocumentBuilder(page_size=page_size, orientation=orientation)
        doc.add_company_header(company)
        doc.add_document_title("Treasury Transfer", subtitle=xfr.transfer_number)
        doc.add_key_value_grid([
            ("Transfer #", xfr.transfer_number),
            ("From Account", xfr.from_account_name),
            ("To Account", xfr.to_account_name),
            ("Date", self._fmt_date(xfr.transfer_date)),
            ("Currency", xfr.currency_code),
            ("Exchange Rate", str(xfr.exchange_rate) if xfr.exchange_rate else "—"),
            ("Amount", self._fmt_amount(xfr.amount)),
            ("Reference", xfr.reference_number or "—"),
            ("Status", xfr.status_code.title()),
        ])
        doc.add_summary_pairs([
            ("Transfer Amount", self._fmt_amount(xfr.amount)),
        ])
        if xfr.description:
            doc.add_section_title("Description")
            doc.add_paragraph(xfr.description, italic=True)
        if xfr.notes:
            doc.add_section_title("Notes")
            doc.add_paragraph(xfr.notes, italic=True)
        return doc

    # ── Detail Excel ────────────────────────────────────────────────────────────

    def _detail_excel(
        self,
        company: CompanyHeaderData,
        xfr: TreasuryTransferDetailDTO,
        page_size: PageSize,
        orientation,
    ) -> "ExcelWorkbookBuilder":
        from seeker_accounting.platform.printing.excel_builder import ExcelWorkbookBuilder

        wb = ExcelWorkbookBuilder(page_size=page_size, orientation=orientation)
        sh = wb.add_sheet("Transfer")
        sh.write_document_header(company, f"Treasury Transfer — {xfr.transfer_number}")
        sh.write_key_value_pairs([
            ("From Account", xfr.from_account_name),
            ("To Account", xfr.to_account_name),
            ("Date", self._fmt_date(xfr.transfer_date)),
            ("Currency", xfr.currency_code),
            ("Exchange Rate", str(xfr.exchange_rate) if xfr.exchange_rate else "—"),
            ("Amount", self._fmt_amount(xfr.amount)),
            ("Reference", xfr.reference_number or "—"),
            ("Status", xfr.status_code.title()),
        ])
        sh.write_branded_footer()
        return wb

    # ── List HTML ───────────────────────────────────────────────────────────────

    def _list_html(
        self,
        company: CompanyHeaderData,
        transfers: list[TreasuryTransferListItemDTO],
        page_size: PageSize,
    ) -> str:
        parts: list[str] = [
            build_company_header(company),
            build_document_title_block(
                "Treasury Transfer Register",
                subtitle=f"{len(transfers)} transfer(s)",
            ),
        ]
        cols = ["Number", "From Account", "To Account", "Date", "Currency", "Amount", "Status", "Reference"]
        rows = [
            [
                t.transfer_number,
                t.from_account_name,
                t.to_account_name,
                self._fmt_date(t.transfer_date),
                t.currency_code,
                self._fmt_amount(t.amount),
                t.status_code.title(),
                t.reference_number or "",
            ]
            for t in transfers
        ]
        total_amount = sum(t.amount for t in transfers)
        total_row = [
            f"{len(transfers)} transfers", "", "", "", "",
            fmt_decimal(total_amount),
            "", "",
        ]
        parts.append(build_data_table(
            cols, rows,
            numeric_columns={5},
            total_row=total_row,
            nowrap_columns={0, 3, 4, 6},
            column_widths={
                0: "14%",
                1: "20%",
                2: "20%",
                3: "10%",
                4: "8%",
                5: "10%",
                6: "8%",
                7: "10%",
            },
        ))
        return wrap_html("".join(parts), page_size=page_size)

    # ── List Word ───────────────────────────────────────────────────────────────

    def _list_word(
        self,
        company: CompanyHeaderData,
        transfers: list[TreasuryTransferListItemDTO],
        page_size: PageSize,
        orientation,
    ) -> "WordDocumentBuilder":
        from seeker_accounting.platform.printing.word_builder import WordDocumentBuilder

        doc = WordDocumentBuilder(page_size=page_size, orientation=orientation)
        doc.add_company_header(company)
        doc.add_document_title(
            "Treasury Transfer Register",
            subtitle=f"{len(transfers)} transfer(s)",
        )
        cols = ["Number", "From Account", "To Account", "Date", "Currency", "Amount", "Status", "Reference"]
        rows = [
            [
                t.transfer_number,
                t.from_account_name,
                t.to_account_name,
                self._fmt_date(t.transfer_date),
                t.currency_code,
                self._fmt_amount(t.amount),
                t.status_code.title(),
                t.reference_number or "",
            ]
            for t in transfers
        ]
        total_amount = sum(t.amount for t in transfers)
        doc.add_data_table(
            cols, rows,
            numeric_columns={5},
            total_row=[
                f"{len(transfers)} transfers", "", "", "", "",
                fmt_decimal(total_amount),
                "", "",
            ],
        )
        return doc

    # ── List Excel ──────────────────────────────────────────────────────────────

    def _list_excel(
        self,
        company: CompanyHeaderData,
        transfers: list[TreasuryTransferListItemDTO],
        page_size: PageSize,
        orientation,
    ) -> "ExcelWorkbookBuilder":
        from seeker_accounting.platform.printing.excel_builder import ExcelWorkbookBuilder

        wb = ExcelWorkbookBuilder(page_size=page_size, orientation=orientation)
        sh = wb.add_sheet("Transfer Register")
        sh.write_document_header(company, "Treasury Transfer Register")
        sh.write_blank_row()
        sh.write_table_header([
            "Number", "From Account", "To Account", "Date", "Currency", "Amount", "Status", "Reference",
        ])
        for t in transfers:
            sh.write_table_row([
                t.transfer_number,
                t.from_account_name,
                t.to_account_name,
                self._fmt_date(t.transfer_date),
                t.currency_code,
                t.amount,
                t.status_code.title(),
                t.reference_number or "",
            ], numeric_columns={5})
        sh.write_totals_row([
            f"{len(transfers)} transfers", "", "", "", "",
            sum(t.amount for t in transfers),
            "", "",
        ])
        sh.write_branded_footer()
        sh.set_column_widths({1: 16, 2: 24, 3: 24, 4: 14, 5: 10, 6: 18, 7: 10, 8: 16})
        return wb
