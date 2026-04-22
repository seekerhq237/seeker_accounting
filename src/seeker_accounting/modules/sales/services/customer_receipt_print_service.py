"""Print and export service for Customer Receipts and Receipt Register.

Handles all three output formats (PDF, Word, Excel) for:
  - Single customer receipt voucher
  - Customer receipt register list
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from seeker_accounting.modules.companies.dto.company_dto import CompanyDetailDTO
from seeker_accounting.modules.sales.dto.customer_receipt_dto import (
    CustomerReceiptDetailDTO,
    CustomerReceiptListItemDTO,
)
from seeker_accounting.platform.printing.html_builder import (
    build_company_header,
    build_data_table,
    build_document_title_block,
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
    from seeker_accounting.modules.sales.services.customer_receipt_service import CustomerReceiptService
    from seeker_accounting.platform.printing.excel_builder import ExcelWorkbookBuilder
    from seeker_accounting.platform.printing.print_engine import PrintEngine
    from seeker_accounting.platform.printing.word_builder import WordDocumentBuilder


class CustomerReceiptPrintService:
    """Renders customer receipt documents to PDF, Word, or Excel."""

    def __init__(
        self,
        print_engine: "PrintEngine",
        customer_receipt_service: "CustomerReceiptService",
        company_service: "CompanyService",
        company_logo_service: "CompanyLogoService",
    ) -> None:
        self._engine = print_engine
        self._receipt_service = customer_receipt_service
        self._company_service = company_service
        self._logo_service = company_logo_service

    # ── Public API ──────────────────────────────────────────────────────────────

    def print_receipt(
        self,
        company_id: int,
        receipt_id: int,
        result: PrintExportResult,
    ) -> None:
        """Render a single customer receipt to the chosen format and path."""
        receipt = self._receipt_service.get_customer_receipt(company_id, receipt_id)
        company = self._company_service.get_company(company_id)
        header = self._make_company_header(company)

        if result.format == PrintFormat.PDF:
            html = self._receipt_html(header, receipt, result.page_size)
            self._engine.render_pdf(
                html, result.output_path,
                page_size=result.page_size,
                orientation=result.orientation,
            )
        elif result.format == PrintFormat.WORD:
            doc = self._receipt_word(header, receipt, result.page_size, result.orientation)
            doc.save(result.output_path)
        else:
            wb = self._receipt_excel(header, receipt, result.page_size, result.orientation)
            wb.save(result.output_path)

    def print_receipt_list(
        self,
        company_id: int,
        receipts: list[CustomerReceiptListItemDTO],
        result: PrintExportResult,
    ) -> None:
        """Render the receipt register list to the chosen format and path."""
        company = self._company_service.get_company(company_id)
        header = self._make_company_header(company)

        if result.format == PrintFormat.PDF:
            html = self._receipt_list_html(header, receipts, result.page_size)
            self._engine.render_pdf(
                html, result.output_path,
                page_size=result.page_size,
                orientation=result.orientation,
            )
        elif result.format == PrintFormat.WORD:
            doc = self._receipt_list_word(header, receipts, result.page_size, result.orientation)
            doc.save(result.output_path)
        else:
            wb = self._receipt_list_excel(header, receipts, result.page_size, result.orientation)
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

    def _receipt_html(
        self,
        company: CompanyHeaderData,
        receipt: CustomerReceiptDetailDTO,
        page_size: PageSize,
    ) -> str:
        parts: list[str] = [
            build_company_header(company),
            build_document_title_block("Customer Receipt", subtitle=receipt.receipt_number),
            self._received_from_section(receipt),
        ]

        # Allocations table
        if receipt.allocations:
            parts.append(build_section_title("Invoice Allocations"))
            alloc_cols = ["Invoice #", "Invoice Date", "Due Date", "Currency", "Invoice Total", "Allocated"]
            alloc_rows = [
                [
                    a.sales_invoice_number,
                    self._fmt_date(a.sales_invoice_date),
                    self._fmt_date(a.sales_invoice_due_date),
                    a.invoice_currency_code,
                    self._fmt_amount(a.invoice_total_amount),
                    self._fmt_amount(a.allocated_amount),
                ]
                for a in receipt.allocations
            ]
            total_allocated = sum(a.allocated_amount for a in receipt.allocations)
            parts.append(build_data_table(
                alloc_cols, alloc_rows,
                numeric_columns={4, 5},
                total_row=["", "", "", "", "TOTAL ALLOCATED", fmt_decimal(total_allocated)],
            ))

        # Totals summary
        summary = build_summary_box([
            ("Amount Received", self._fmt_amount(receipt.amount_received)),
            ("Allocated", self._fmt_amount(receipt.allocated_amount)),
            ("Unallocated", self._fmt_amount(receipt.remaining_unallocated_amount)),
        ], highlight_last=False)
        parts.append(
            '<table style="width:100%;"><tr>'
            '<td style="vertical-align:top;width:50%;"></td>'
            f'<td style="vertical-align:top;width:50%;">{summary}</td>'
            '</tr></table>'
        )

        if receipt.notes:
            parts.append(build_section_title("Notes"))
            parts.append(
                f'<p style="font-size:9pt;color:#444;margin:4px 0;">{h(receipt.notes)}</p>'
            )

        return wrap_html("".join(parts), page_size=page_size)

    def _received_from_section(self, receipt: CustomerReceiptDetailDTO) -> str:
        """Two-column header: Received From (left) | Receipt Details (right)."""
        left = (
            '<div style="font-size:7pt;text-transform:uppercase;font-weight:700;'
            'color:#6b7280;letter-spacing:0.5px;margin-bottom:4px;">Received From</div>'
            f'<div style="font-weight:700;font-size:11pt;color:#1a1a1a;margin-bottom:2px;">'
            f'{h(receipt.customer_name)}</div>'
            f'<div style="font-size:9pt;color:#6b7280;">{h(receipt.customer_code)}</div>'
        )
        detail_rows = "".join(
            f'<tr>'
            f'<td style="font-size:7.5pt;color:#6b7280;text-transform:uppercase;'
            f'letter-spacing:0.3px;padding:2px 10px 2px 0;white-space:nowrap;width:40%;">{h(k)}</td>'
            f'<td style="font-size:9pt;font-weight:600;color:#1a1a1a;padding:2px 0;">{h(v)}</td>'
            f'</tr>'
            for k, v in [
                ("Receipt #", receipt.receipt_number),
                ("Date", self._fmt_date(receipt.receipt_date)),
                ("Account", receipt.financial_account_name),
                ("Currency", receipt.currency_code),
                ("Reference", receipt.reference_number or "—"),
                ("Status", receipt.status_code.title()),
            ]
        )
        right = f'<table style="width:100%;border-collapse:collapse;">{detail_rows}</table>'

        return (
            '<table style="width:100%;border-collapse:collapse;margin-bottom:14px;">'
            '<tr>'
            f'<td style="vertical-align:top;width:46%;padding-right:14px;">{left}</td>'
            '<td style="width:8px;border-left:1px solid #d0d7de;"></td>'
            f'<td style="vertical-align:top;width:46%;padding-left:14px;">{right}</td>'
            '</tr>'
            '</table>'
        )

    def _receipt_list_html(
        self,
        company: CompanyHeaderData,
        receipts: list[CustomerReceiptListItemDTO],
        page_size: PageSize,
    ) -> str:
        parts: list[str] = [
            build_company_header(company),
            build_document_title_block(
                "Customer Receipt Register",
                subtitle=f"{len(receipts)} receipt(s)",
            ),
        ]
        cols = ["Receipt #", "Date", "Customer", "Account", "Currency", "Amount", "Status", "Posted At"]
        rows = [
            [
                r.receipt_number,
                self._fmt_date(r.receipt_date),
                r.customer_name,
                r.financial_account_name,
                r.currency_code,
                self._fmt_amount(r.amount_received),
                r.status_code.title(),
                r.posted_at.strftime("%d/%m/%Y") if r.posted_at else "—",
            ]
            for r in receipts
        ]
        total_amount = sum(r.amount_received for r in receipts)
        total_row = [
            "TOTALS", "", f"{len(receipts)} receipts", "", "",
            fmt_decimal(total_amount),
            "", "",
        ]
        parts.append(build_data_table(
            cols, rows,
            numeric_columns={5},
            total_row=total_row,
            nowrap_columns={0, 1, 4, 6, 7},
            column_widths={
                0: "14%",
                1: "10%",
                2: "22%",
                3: "20%",
                4: "8%",
                5: "10%",
                6: "8%",
                7: "8%",
            },
        ))
        return wrap_html("".join(parts), page_size=page_size)

    # ── Word builders ───────────────────────────────────────────────────────────

    def _receipt_word(
        self,
        company: CompanyHeaderData,
        receipt: CustomerReceiptDetailDTO,
        page_size: PageSize,
        orientation,
    ) -> "WordDocumentBuilder":
        from seeker_accounting.platform.printing.word_builder import WordDocumentBuilder

        doc = WordDocumentBuilder(page_size=page_size, orientation=orientation)
        doc.add_company_header(company)
        doc.add_document_title("Customer Receipt", subtitle=receipt.receipt_number)
        doc.add_key_value_grid([
            ("Customer", receipt.customer_name),
            ("Customer Code", receipt.customer_code),
            ("Receipt #", receipt.receipt_number),
            ("Date", self._fmt_date(receipt.receipt_date)),
            ("Cash/Bank Account", receipt.financial_account_name),
            ("Currency", receipt.currency_code),
            ("Reference", receipt.reference_number or "—"),
            ("Status", receipt.status_code.title()),
        ])

        if receipt.allocations:
            doc.add_section_title("Invoice Allocations")
            alloc_cols = ["Invoice #", "Invoice Date", "Due Date", "Currency", "Invoice Total", "Allocated"]
            alloc_rows = [
                [
                    a.sales_invoice_number,
                    self._fmt_date(a.sales_invoice_date),
                    self._fmt_date(a.sales_invoice_due_date),
                    a.invoice_currency_code,
                    self._fmt_amount(a.invoice_total_amount),
                    self._fmt_amount(a.allocated_amount),
                ]
                for a in receipt.allocations
            ]
            doc.add_data_table(
                alloc_cols, alloc_rows,
                numeric_columns={4, 5},
                total_row=["", "", "", "", "TOTAL",
                           fmt_decimal(sum(a.allocated_amount for a in receipt.allocations))],
            )

        doc.add_summary_pairs([
            ("Amount Received", self._fmt_amount(receipt.amount_received)),
            ("Allocated", self._fmt_amount(receipt.allocated_amount)),
            ("Unallocated", self._fmt_amount(receipt.remaining_unallocated_amount)),
        ])

        if receipt.notes:
            doc.add_section_title("Notes")
            doc.add_paragraph(receipt.notes, italic=True)

        return doc

    def _receipt_list_word(
        self,
        company: CompanyHeaderData,
        receipts: list[CustomerReceiptListItemDTO],
        page_size: PageSize,
        orientation,
    ) -> "WordDocumentBuilder":
        from seeker_accounting.platform.printing.word_builder import WordDocumentBuilder

        doc = WordDocumentBuilder(page_size=page_size, orientation=orientation)
        doc.add_company_header(company)
        doc.add_document_title("Customer Receipt Register", subtitle=f"{len(receipts)} receipt(s)")
        cols = ["Receipt #", "Date", "Customer", "Account", "Currency", "Amount", "Status"]
        rows = [
            [
                r.receipt_number,
                self._fmt_date(r.receipt_date),
                r.customer_name,
                r.financial_account_name,
                r.currency_code,
                self._fmt_amount(r.amount_received),
                r.status_code.title(),
            ]
            for r in receipts
        ]
        doc.add_data_table(
            cols, rows,
            numeric_columns={5},
            total_row=[
                "TOTALS", "", f"{len(receipts)} receipts", "", "",
                fmt_decimal(sum(r.amount_received for r in receipts)),
                "",
            ],
        )
        return doc

    # ── Excel builders ──────────────────────────────────────────────────────────

    def _receipt_excel(
        self,
        company: CompanyHeaderData,
        receipt: CustomerReceiptDetailDTO,
        page_size: PageSize,
        orientation,
    ) -> "ExcelWorkbookBuilder":
        from seeker_accounting.platform.printing.excel_builder import ExcelWorkbookBuilder

        wb = ExcelWorkbookBuilder(page_size=page_size, orientation=orientation)
        sh = wb.add_sheet("Receipt")
        sh.write_document_header(company, f"Customer Receipt — {receipt.receipt_number}")
        sh.write_key_value_pairs([
            ("Customer", receipt.customer_name),
            ("Date", self._fmt_date(receipt.receipt_date)),
            ("Cash/Bank Account", receipt.financial_account_name),
            ("Currency", receipt.currency_code),
            ("Reference", receipt.reference_number or "—"),
            ("Status", receipt.status_code.title()),
        ])
        sh.write_blank_row()

        if receipt.allocations:
            sh.write_table_header(["Invoice #", "Invoice Date", "Due Date", "Currency", "Invoice Total", "Allocated"])
            for a in receipt.allocations:
                sh.write_table_row([
                    a.sales_invoice_number,
                    self._fmt_date(a.sales_invoice_date),
                    self._fmt_date(a.sales_invoice_due_date),
                    a.invoice_currency_code,
                    a.invoice_total_amount,
                    a.allocated_amount,
                ], numeric_columns={4, 5})
            sh.write_totals_row([
                "", "", "", "", "Total Allocated",
                sum(a.allocated_amount for a in receipt.allocations),
            ])
            sh.write_blank_row()

        sh.write_totals_row(["Amount Received", "", "", "", "", receipt.amount_received])
        sh.write_totals_row(["Allocated", "", "", "", "", receipt.allocated_amount])
        sh.write_totals_row(["Unallocated", "", "", "", "", receipt.remaining_unallocated_amount])
        sh.write_branded_footer()
        return wb

    def _receipt_list_excel(
        self,
        company: CompanyHeaderData,
        receipts: list[CustomerReceiptListItemDTO],
        page_size: PageSize,
        orientation,
    ) -> "ExcelWorkbookBuilder":
        from seeker_accounting.platform.printing.excel_builder import ExcelWorkbookBuilder

        wb = ExcelWorkbookBuilder(page_size=page_size, orientation=orientation)
        sh = wb.add_sheet("Receipt Register")
        sh.write_document_header(company, "Customer Receipt Register")
        sh.write_blank_row()
        sh.write_table_header(["Receipt #", "Date", "Customer", "Account", "Currency", "Amount", "Status", "Posted At"])
        for r in receipts:
            sh.write_table_row([
                r.receipt_number,
                self._fmt_date(r.receipt_date),
                r.customer_name,
                r.financial_account_name,
                r.currency_code,
                r.amount_received,
                r.status_code.title(),
                r.posted_at.strftime("%d/%m/%Y") if r.posted_at else "",
            ], numeric_columns={5})
        sh.write_totals_row([
            "TOTALS", "", f"{len(receipts)} receipts", "", "",
            sum(r.amount_received for r in receipts),
            "", "",
        ])
        sh.write_branded_footer()
        return wb
