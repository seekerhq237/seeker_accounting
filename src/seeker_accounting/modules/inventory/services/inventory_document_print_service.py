"""Print and export service for Inventory Documents and Document Register.

Handles all three output formats (PDF, Word, Excel) for:
  - Single inventory document detail
  - Inventory document register list
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from seeker_accounting.modules.companies.dto.company_dto import CompanyDetailDTO
from seeker_accounting.modules.inventory.dto.inventory_document_dto import (
    InventoryDocumentDetailDTO,
    InventoryDocumentListItemDTO,
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
    from seeker_accounting.modules.inventory.services.inventory_document_service import InventoryDocumentService
    from seeker_accounting.platform.printing.excel_builder import ExcelWorkbookBuilder
    from seeker_accounting.platform.printing.print_engine import PrintEngine
    from seeker_accounting.platform.printing.word_builder import WordDocumentBuilder


class InventoryDocumentPrintService:
    """Renders inventory document records to PDF, Word, or Excel."""

    def __init__(
        self,
        print_engine: "PrintEngine",
        inventory_document_service: "InventoryDocumentService",
        company_service: "CompanyService",
        company_logo_service: "CompanyLogoService",
    ) -> None:
        self._engine = print_engine
        self._doc_service = inventory_document_service
        self._company_service = company_service
        self._logo_service = company_logo_service

    # ── Public API ──────────────────────────────────────────────────────────────

    def print_document(
        self,
        company_id: int,
        document_id: int,
        result: PrintExportResult,
    ) -> None:
        """Render a single inventory document to the chosen format and path."""
        inv_doc = self._doc_service.get_inventory_document(company_id, document_id)
        company = self._company_service.get_company(company_id)
        header = self._make_company_header(company)

        if result.format == PrintFormat.PDF:
            html = self._detail_html(header, inv_doc, result.page_size)
            self._engine.render_pdf(
                html, result.output_path,
                page_size=result.page_size,
                orientation=result.orientation,
            )
        elif result.format == PrintFormat.WORD:
            doc = self._detail_word(header, inv_doc, result.page_size, result.orientation)
            doc.save(result.output_path)
        else:
            wb = self._detail_excel(header, inv_doc, result.page_size, result.orientation)
            wb.save(result.output_path)

    def print_document_list(
        self,
        company_id: int,
        documents: list[InventoryDocumentListItemDTO],
        result: PrintExportResult,
    ) -> None:
        """Render the inventory document register (list) to the chosen format and path."""
        company = self._company_service.get_company(company_id)
        header = self._make_company_header(company)

        if result.format == PrintFormat.PDF:
            html = self._list_html(header, documents, result.page_size)
            self._engine.render_pdf(
                html, result.output_path,
                page_size=result.page_size,
                orientation=result.orientation,
            )
        elif result.format == PrintFormat.WORD:
            doc = self._list_word(header, documents, result.page_size, result.orientation)
            doc.save(result.output_path)
        else:
            wb = self._list_excel(header, documents, result.page_size, result.orientation)
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

    @staticmethod
    def _fmt_qty(v: Decimal | None) -> str:
        return fmt_decimal(v, 4) if v is not None else "—"

    # ── Detail HTML ─────────────────────────────────────────────────────────────

    def _detail_html(
        self,
        company: CompanyHeaderData,
        inv_doc: InventoryDocumentDetailDTO,
        page_size: PageSize,
    ) -> str:
        parts: list[str] = [
            build_company_header(company),
            build_document_title_block("Inventory Document", subtitle=inv_doc.document_number),
            build_key_value_grid([
                ("Document #", inv_doc.document_number),
                ("Type", inv_doc.document_type_code.replace("_", " ").title()),
                ("Date", self._fmt_date(inv_doc.document_date)),
                ("Reference", inv_doc.reference_number or "—"),
                ("Status", inv_doc.status_code.title()),
            ]),
        ]

        if inv_doc.lines:
            parts.append(build_section_title("Line Items"))
            line_cols = ["#", "Item", "Description", "Qty", "Unit Cost", "Amount"]
            line_rows = [
                [
                    str(ln.line_number),
                    f"{ln.item_code} — {ln.item_name}",
                    ln.line_description or "",
                    self._fmt_qty(ln.quantity),
                    self._fmt_amount(ln.unit_cost),
                    self._fmt_amount(ln.line_amount),
                ]
                for ln in inv_doc.lines
            ]
            trailing = ["", "", "", "", "TOTAL", self._fmt_amount(inv_doc.total_value)]
            parts.append(build_data_table(
                line_cols, line_rows,
                numeric_columns={3, 4, 5},
                total_row=trailing,
            ))

        summary = build_summary_box([
            ("Total Value", self._fmt_amount(inv_doc.total_value)),
        ], highlight_last=False)
        parts.append(
            '<table style="width:100%;"><tr>'
            '<td style="vertical-align:top;width:50%;"></td>'
            f'<td style="vertical-align:top;width:50%;">{summary}</td>'
            '</tr></table>'
        )

        if inv_doc.notes:
            parts.append(build_section_title("Notes"))
            parts.append(
                f'<p style="font-size:9pt;color:#444;margin:4px 0;">{h(inv_doc.notes)}</p>'
            )

        return wrap_html("".join(parts), page_size=page_size)

    # ── Detail Word ─────────────────────────────────────────────────────────────

    def _detail_word(
        self,
        company: CompanyHeaderData,
        inv_doc: InventoryDocumentDetailDTO,
        page_size: PageSize,
        orientation,
    ) -> "WordDocumentBuilder":
        from seeker_accounting.platform.printing.word_builder import WordDocumentBuilder

        doc = WordDocumentBuilder(page_size=page_size, orientation=orientation)
        doc.add_company_header(company)
        doc.add_document_title("Inventory Document", subtitle=inv_doc.document_number)
        doc.add_key_value_grid([
            ("Document #", inv_doc.document_number),
            ("Type", inv_doc.document_type_code.replace("_", " ").title()),
            ("Date", self._fmt_date(inv_doc.document_date)),
            ("Reference", inv_doc.reference_number or "—"),
            ("Status", inv_doc.status_code.title()),
        ])

        if inv_doc.lines:
            doc.add_section_title("Line Items")
            line_cols = ["#", "Item", "Description", "Qty", "Unit Cost", "Amount"]
            line_rows = [
                [
                    str(ln.line_number),
                    f"{ln.item_code} — {ln.item_name}",
                    ln.line_description or "",
                    self._fmt_qty(ln.quantity),
                    self._fmt_amount(ln.unit_cost),
                    self._fmt_amount(ln.line_amount),
                ]
                for ln in inv_doc.lines
            ]
            doc.add_data_table(
                line_cols, line_rows,
                numeric_columns={3, 4, 5},
                total_row=["", "", "", "", "TOTAL", self._fmt_amount(inv_doc.total_value)],
            )

        doc.add_summary_pairs([
            ("Total Value", self._fmt_amount(inv_doc.total_value)),
        ])

        if inv_doc.notes:
            doc.add_section_title("Notes")
            doc.add_paragraph(inv_doc.notes, italic=True)
        return doc

    # ── Detail Excel ────────────────────────────────────────────────────────────

    def _detail_excel(
        self,
        company: CompanyHeaderData,
        inv_doc: InventoryDocumentDetailDTO,
        page_size: PageSize,
        orientation,
    ) -> "ExcelWorkbookBuilder":
        from seeker_accounting.platform.printing.excel_builder import ExcelWorkbookBuilder

        wb = ExcelWorkbookBuilder(page_size=page_size, orientation=orientation)
        sh = wb.add_sheet("Document")
        sh.write_document_header(company, f"Inventory Document — {inv_doc.document_number}")
        sh.write_key_value_pairs([
            ("Type", inv_doc.document_type_code.replace("_", " ").title()),
            ("Date", self._fmt_date(inv_doc.document_date)),
            ("Reference", inv_doc.reference_number or "—"),
            ("Status", inv_doc.status_code.title()),
        ])
        sh.write_blank_row()
        sh.write_table_header(["#", "Item", "Description", "Qty", "Unit Cost", "Amount"])
        for ln in inv_doc.lines:
            sh.write_table_row([
                ln.line_number,
                f"{ln.item_code} — {ln.item_name}",
                ln.line_description or "",
                ln.quantity,
                ln.unit_cost,
                ln.line_amount,
            ], numeric_columns={3, 4, 5})
        sh.write_totals_row(["", "", "", "", "Total Value", inv_doc.total_value])
        sh.write_branded_footer()
        return wb

    # ── List HTML ───────────────────────────────────────────────────────────────

    def _list_html(
        self,
        company: CompanyHeaderData,
        documents: list[InventoryDocumentListItemDTO],
        page_size: PageSize,
    ) -> str:
        parts: list[str] = [
            build_company_header(company),
            build_document_title_block(
                "Inventory Document Register",
                subtitle=f"{len(documents)} document(s)",
            ),
        ]
        cols = ["Number", "Type", "Date", "Reference", "Total Value", "Status"]
        rows = [
            [
                d.document_number,
                d.document_type_code.replace("_", " ").title(),
                self._fmt_date(d.document_date),
                d.reference_number or "",
                self._fmt_amount(d.total_value),
                d.status_code.title(),
            ]
            for d in documents
        ]
        total_value = sum(d.total_value for d in documents)
        total_row = [
            f"{len(documents)} documents", "", "", "",
            fmt_decimal(total_value),
            "",
        ]
        parts.append(build_data_table(
            cols, rows,
            numeric_columns={4},
            total_row=total_row,
            nowrap_columns={0, 2, 5},
            column_widths={
                0: "18%",
                1: "18%",
                2: "12%",
                3: "22%",
                4: "14%",
                5: "16%",
            },
        ))
        return wrap_html("".join(parts), page_size=page_size)

    # ── List Word ───────────────────────────────────────────────────────────────

    def _list_word(
        self,
        company: CompanyHeaderData,
        documents: list[InventoryDocumentListItemDTO],
        page_size: PageSize,
        orientation,
    ) -> "WordDocumentBuilder":
        from seeker_accounting.platform.printing.word_builder import WordDocumentBuilder

        doc = WordDocumentBuilder(page_size=page_size, orientation=orientation)
        doc.add_company_header(company)
        doc.add_document_title(
            "Inventory Document Register",
            subtitle=f"{len(documents)} document(s)",
        )
        cols = ["Number", "Type", "Date", "Reference", "Total Value", "Status"]
        rows = [
            [
                d.document_number,
                d.document_type_code.replace("_", " ").title(),
                self._fmt_date(d.document_date),
                d.reference_number or "",
                self._fmt_amount(d.total_value),
                d.status_code.title(),
            ]
            for d in documents
        ]
        total_value = sum(d.total_value for d in documents)
        doc.add_data_table(
            cols, rows,
            numeric_columns={4},
            total_row=[
                f"{len(documents)} documents", "", "", "",
                fmt_decimal(total_value),
                "",
            ],
        )
        return doc

    # ── List Excel ──────────────────────────────────────────────────────────────

    def _list_excel(
        self,
        company: CompanyHeaderData,
        documents: list[InventoryDocumentListItemDTO],
        page_size: PageSize,
        orientation,
    ) -> "ExcelWorkbookBuilder":
        from seeker_accounting.platform.printing.excel_builder import ExcelWorkbookBuilder

        wb = ExcelWorkbookBuilder(page_size=page_size, orientation=orientation)
        sh = wb.add_sheet("Document Register")
        sh.write_document_header(company, "Inventory Document Register")
        sh.write_blank_row()
        sh.write_table_header(["Number", "Type", "Date", "Reference", "Total Value", "Status"])
        for d in documents:
            sh.write_table_row([
                d.document_number,
                d.document_type_code.replace("_", " ").title(),
                self._fmt_date(d.document_date),
                d.reference_number or "",
                d.total_value,
                d.status_code.title(),
            ], numeric_columns={4})
        sh.write_totals_row([
            f"{len(documents)} documents", "", "", "",
            sum(d.total_value for d in documents),
            "",
        ])
        sh.write_branded_footer()
        sh.set_column_widths({1: 16, 2: 14, 3: 14, 4: 16, 5: 18, 6: 10})
        return wb
