"""Print and export service for Sales Invoices and Invoice Register.

Handles all three output formats (PDF, Word, Excel) for:
  - Single sales invoice detail document
  - Sales invoice register list

Architecture: UI calls print_invoice() / print_invoice_list() with a
PrintExportResult from PrintExportDialog. This service fetches the data,
builds the content via platform builders, and delegates rendering to PrintEngine.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from seeker_accounting.modules.companies.dto.company_dto import CompanyDetailDTO
from seeker_accounting.modules.sales.dto.sales_invoice_dto import (
    SalesInvoiceDetailDTO,
    SalesInvoiceListItemDTO,
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
    from seeker_accounting.modules.sales.services.sales_invoice_service import SalesInvoiceService
    from seeker_accounting.platform.printing.excel_builder import ExcelWorkbookBuilder
    from seeker_accounting.platform.printing.print_engine import PrintEngine
    from seeker_accounting.platform.printing.word_builder import WordDocumentBuilder


class SalesInvoicePrintService:
    """Renders sales invoice documents to PDF, Word, or Excel."""

    def __init__(
        self,
        print_engine: "PrintEngine",
        sales_invoice_service: "SalesInvoiceService",
        company_service: "CompanyService",
        company_logo_service: "CompanyLogoService",
    ) -> None:
        self._engine = print_engine
        self._invoice_service = sales_invoice_service
        self._company_service = company_service
        self._logo_service = company_logo_service

    # ── Public API ──────────────────────────────────────────────────────────────

    def print_invoice(
        self,
        company_id: int,
        invoice_id: int,
        result: PrintExportResult,
    ) -> None:
        """Render a single sales invoice to the chosen format and path."""
        invoice = self._invoice_service.get_sales_invoice(company_id, invoice_id)
        company = self._company_service.get_company(company_id)
        header = self._make_company_header(company)

        if result.format == PrintFormat.PDF:
            html = self._invoice_html(header, invoice, result.page_size)
            self._engine.render_pdf(
                html, result.output_path,
                page_size=result.page_size,
                orientation=result.orientation,
            )
        elif result.format == PrintFormat.WORD:
            doc = self._invoice_word(header, invoice, result.page_size, result.orientation)
            doc.save(result.output_path)
        else:
            wb = self._invoice_excel(header, invoice, result.page_size, result.orientation)
            wb.save(result.output_path)

    def print_invoice_list(
        self,
        company_id: int,
        invoices: list[SalesInvoiceListItemDTO],
        result: PrintExportResult,
    ) -> None:
        """Render the invoice register (list) to the chosen format and path."""
        company = self._company_service.get_company(company_id)
        header = self._make_company_header(company)

        if result.format == PrintFormat.PDF:
            html = self._invoice_list_html(header, invoices, result.page_size)
            self._engine.render_pdf(
                html, result.output_path,
                page_size=result.page_size,
                orientation=result.orientation,
            )
        elif result.format == PrintFormat.WORD:
            doc = self._invoice_list_word(header, invoices, result.page_size, result.orientation)
            doc.save(result.output_path)
        else:
            wb = self._invoice_list_excel(header, invoices, result.page_size, result.orientation)
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

    def _invoice_html(
        self,
        company: CompanyHeaderData,
        invoice: SalesInvoiceDetailDTO,
        page_size: PageSize,
    ) -> str:
        parts: list[str] = [
            build_company_header(company),
            build_document_title_block("Sales Invoice", subtitle=invoice.invoice_number),
            self._bill_to_section(invoice),
        ]

        # Line items
        parts.append(build_section_title("Line Items"))
        line_cols = ["#", "Description", "Qty", "Unit Price", "Disc.", "Tax", "Subtotal", "Tax Amt", "Total"]
        line_rows = [
            [
                str(ln.line_number),
                ln.description,
                fmt_decimal(ln.quantity, 2),
                self._fmt_amount(ln.unit_price),
                f"{ln.discount_percent:.2f}%" if ln.discount_percent else "—",
                ln.tax_code_code or "—",
                self._fmt_amount(ln.line_subtotal_amount),
                self._fmt_amount(ln.line_tax_amount),
                self._fmt_amount(ln.line_total_amount),
            ]
            for ln in invoice.lines
        ]
        trailing_total = ["", "", "", "", "", "", "", "TOTAL", self._fmt_amount(invoice.totals.total_amount)]
        parts.append(build_data_table(
            line_cols, line_rows,
            numeric_columns={2, 3, 6, 7, 8},
            total_row=trailing_total,
        ))

        # Totals summary aligned right
        summary = build_summary_box([
            ("Subtotal", self._fmt_amount(invoice.totals.subtotal_amount)),
            ("Tax", self._fmt_amount(invoice.totals.tax_amount)),
            ("Grand Total", self._fmt_amount(invoice.totals.total_amount)),
            ("Allocated", self._fmt_amount(invoice.totals.allocated_amount)),
            ("Open Balance", self._fmt_amount(invoice.totals.open_balance_amount)),
        ], highlight_last=False)
        parts.append(
            '<table style="width:100%;"><tr>'
            '<td style="vertical-align:top;width:50%;"></td>'
            f'<td style="vertical-align:top;width:50%;">{summary}</td>'
            '</tr></table>'
        )

        if invoice.notes:
            parts.append(build_section_title("Notes"))
            parts.append(
                f'<p style="font-size:9pt;color:#444;margin:4px 0;">{h(invoice.notes)}</p>'
            )

        return wrap_html("".join(parts), page_size=page_size)

    def _bill_to_section(self, invoice: SalesInvoiceDetailDTO) -> str:
        """Two-column header: Bill To (left) | Invoice Details (right)."""
        pay_label = {
            "unpaid": "Unpaid",
            "partial": "Partially Paid",
            "paid": "Paid",
        }.get(invoice.payment_status_code, invoice.payment_status_code.title())

        left = (
            '<div style="font-size:7pt;text-transform:uppercase;font-weight:700;'
            'color:#6b7280;letter-spacing:0.5px;margin-bottom:4px;">Bill To</div>'
            f'<div style="font-weight:700;font-size:11pt;color:#1a1a1a;margin-bottom:2px;">'
            f'{h(invoice.customer_name)}</div>'
            f'<div style="font-size:9pt;color:#6b7280;">{h(invoice.customer_code)}</div>'
        )
        detail_rows = "".join(
            f'<tr>'
            f'<td style="font-size:7.5pt;color:#6b7280;text-transform:uppercase;'
            f'letter-spacing:0.3px;padding:2px 10px 2px 0;white-space:nowrap;width:38%;">{h(k)}</td>'
            f'<td style="font-size:9pt;font-weight:600;color:#1a1a1a;padding:2px 0;">{h(v)}</td>'
            f'</tr>'
            for k, v in [
                ("Invoice #", invoice.invoice_number),
                ("Date", self._fmt_date(invoice.invoice_date)),
                ("Due Date", self._fmt_date(invoice.due_date)),
                ("Currency", invoice.currency_code),
                ("Reference", invoice.reference_number or "—"),
                ("Status", invoice.status_code.title()),
                ("Payment", pay_label),
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

    def _invoice_list_html(
        self,
        company: CompanyHeaderData,
        invoices: list[SalesInvoiceListItemDTO],
        page_size: PageSize,
    ) -> str:
        parts: list[str] = [
            build_company_header(company),
            build_document_title_block(
                "Sales Invoice Register",
                subtitle=f"{len(invoices)} invoice(s)",
            ),
        ]
        cols = [
            "Invoice #", "Date", "Due Date", "Customer", "Curr.",
            "Subtotal", "Tax", "Total", "Open Balance", "Status", "Payment",
        ]
        rows = [
            [
                inv.invoice_number,
                self._fmt_date(inv.invoice_date),
                self._fmt_date(inv.due_date),
                inv.customer_name,
                inv.currency_code,
                self._fmt_amount(inv.subtotal_amount),
                self._fmt_amount(inv.tax_amount),
                self._fmt_amount(inv.total_amount),
                self._fmt_amount(inv.open_balance_amount),
                inv.status_code.title(),
                inv.payment_status_code.title(),
            ]
            for inv in invoices
        ]
        total_subtotal = sum(i.subtotal_amount for i in invoices)
        total_tax = sum(i.tax_amount for i in invoices)
        total_total = sum(i.total_amount for i in invoices)
        total_open = sum(i.open_balance_amount for i in invoices)
        total_row = [
            "TOTALS", "", "", f"{len(invoices)} invoices", "",
            fmt_decimal(total_subtotal),
            fmt_decimal(total_tax),
            fmt_decimal(total_total),
            fmt_decimal(total_open),
            "", "",
        ]
        parts.append(build_data_table(
            cols, rows,
            numeric_columns={5, 6, 7, 8},
            total_row=total_row,
            nowrap_columns={0, 1, 2, 4, 9, 10},
            column_widths={
                0: "11%",
                1: "8%",
                2: "8%",
                3: "19%",
                4: "6%",
                5: "10%",
                6: "8%",
                7: "10%",
                8: "11%",
                9: "5%",
                10: "4%",
            },
        ))
        return wrap_html("".join(parts), page_size=page_size)

    # ── Word builders ───────────────────────────────────────────────────────────

    def _invoice_word(
        self,
        company: CompanyHeaderData,
        invoice: SalesInvoiceDetailDTO,
        page_size: PageSize,
        orientation,
    ) -> "WordDocumentBuilder":
        from seeker_accounting.platform.printing.word_builder import WordDocumentBuilder

        pay_label = {"unpaid": "Unpaid", "partial": "Partially Paid", "paid": "Paid"}.get(
            invoice.payment_status_code, invoice.payment_status_code.title()
        )
        doc = WordDocumentBuilder(page_size=page_size, orientation=orientation)
        doc.add_company_header(company)
        doc.add_document_title("Sales Invoice", subtitle=invoice.invoice_number)
        doc.add_key_value_grid([
            ("Customer", invoice.customer_name),
            ("Customer Code", invoice.customer_code),
            ("Invoice #", invoice.invoice_number),
            ("Invoice Date", self._fmt_date(invoice.invoice_date)),
            ("Due Date", self._fmt_date(invoice.due_date)),
            ("Currency", invoice.currency_code),
            ("Reference", invoice.reference_number or "—"),
            ("Status", invoice.status_code.title()),
            ("Payment", pay_label),
        ])
        doc.add_section_title("Line Items")
        line_cols = ["#", "Description", "Qty", "Unit Price", "Disc.", "Tax", "Subtotal", "Tax Amt", "Total"]
        line_rows = [
            [
                str(ln.line_number),
                ln.description,
                fmt_decimal(ln.quantity, 2),
                self._fmt_amount(ln.unit_price),
                f"{ln.discount_percent:.2f}%" if ln.discount_percent else "—",
                ln.tax_code_code or "—",
                self._fmt_amount(ln.line_subtotal_amount),
                self._fmt_amount(ln.line_tax_amount),
                self._fmt_amount(ln.line_total_amount),
            ]
            for ln in invoice.lines
        ]
        doc.add_data_table(
            line_cols, line_rows,
            numeric_columns={2, 3, 6, 7, 8},
            total_row=["", "", "", "", "", "", "", "TOTAL", self._fmt_amount(invoice.totals.total_amount)],
        )
        doc.add_summary_pairs([
            ("Subtotal", self._fmt_amount(invoice.totals.subtotal_amount)),
            ("Tax Amount", self._fmt_amount(invoice.totals.tax_amount)),
            ("Grand Total", self._fmt_amount(invoice.totals.total_amount)),
            ("Allocated", self._fmt_amount(invoice.totals.allocated_amount)),
            ("Open Balance", self._fmt_amount(invoice.totals.open_balance_amount)),
        ])
        if invoice.notes:
            doc.add_section_title("Notes")
            doc.add_paragraph(invoice.notes, italic=True)
        return doc

    def _invoice_list_word(
        self,
        company: CompanyHeaderData,
        invoices: list[SalesInvoiceListItemDTO],
        page_size: PageSize,
        orientation,
    ) -> "WordDocumentBuilder":
        from seeker_accounting.platform.printing.word_builder import WordDocumentBuilder

        doc = WordDocumentBuilder(page_size=page_size, orientation=orientation)
        doc.add_company_header(company)
        doc.add_document_title("Sales Invoice Register", subtitle=f"{len(invoices)} invoice(s)")
        cols = [
            "Invoice #", "Date", "Due Date", "Customer", "Curr.",
            "Subtotal", "Tax", "Total", "Open Bal.", "Status",
        ]
        rows = [
            [
                inv.invoice_number,
                self._fmt_date(inv.invoice_date),
                self._fmt_date(inv.due_date),
                inv.customer_name,
                inv.currency_code,
                self._fmt_amount(inv.subtotal_amount),
                self._fmt_amount(inv.tax_amount),
                self._fmt_amount(inv.total_amount),
                self._fmt_amount(inv.open_balance_amount),
                inv.status_code.title(),
            ]
            for inv in invoices
        ]
        doc.add_data_table(
            cols, rows,
            numeric_columns={5, 6, 7, 8},
            total_row=[
                "TOTALS", "", "", "", "",
                fmt_decimal(sum(i.subtotal_amount for i in invoices)),
                fmt_decimal(sum(i.tax_amount for i in invoices)),
                fmt_decimal(sum(i.total_amount for i in invoices)),
                fmt_decimal(sum(i.open_balance_amount for i in invoices)),
                "",
            ],
        )
        return doc

    # ── Excel builders ──────────────────────────────────────────────────────────

    def _invoice_excel(
        self,
        company: CompanyHeaderData,
        invoice: SalesInvoiceDetailDTO,
        page_size: PageSize,
        orientation,
    ) -> "ExcelWorkbookBuilder":
        from seeker_accounting.platform.printing.excel_builder import ExcelWorkbookBuilder

        pay_label = {"unpaid": "Unpaid", "partial": "Partially Paid", "paid": "Paid"}.get(
            invoice.payment_status_code, invoice.payment_status_code.title()
        )
        wb = ExcelWorkbookBuilder(page_size=page_size, orientation=orientation)
        sh = wb.add_sheet("Invoice")
        sh.write_document_header(company, f"Sales Invoice — {invoice.invoice_number}")
        sh.write_key_value_pairs([
            ("Customer", invoice.customer_name),
            ("Invoice Date", self._fmt_date(invoice.invoice_date)),
            ("Due Date", self._fmt_date(invoice.due_date)),
            ("Currency", invoice.currency_code),
            ("Reference", invoice.reference_number or "—"),
            ("Status", invoice.status_code.title()),
            ("Payment", pay_label),
        ])
        sh.write_blank_row()
        sh.write_table_header(["#", "Description", "Qty", "Unit Price", "Disc.", "Tax", "Subtotal", "Tax Amt", "Total"])
        for ln in invoice.lines:
            sh.write_table_row([
                ln.line_number,
                ln.description,
                ln.quantity,
                ln.unit_price,
                float(ln.discount_percent) if ln.discount_percent else "",
                ln.tax_code_code or "",
                ln.line_subtotal_amount,
                ln.line_tax_amount,
                ln.line_total_amount,
            ], numeric_columns={2, 3, 4, 6, 7, 8})
        sh.write_totals_row(["", "", "", "", "", "", "Subtotal", "", invoice.totals.subtotal_amount])
        sh.write_totals_row(["", "", "", "", "", "", "Tax", "", invoice.totals.tax_amount])
        sh.write_totals_row(["", "", "", "", "", "", "Grand Total", "", invoice.totals.total_amount])
        sh.write_totals_row(["", "", "", "", "", "", "Allocated", "", invoice.totals.allocated_amount])
        sh.write_totals_row(["", "", "", "", "", "", "Open Balance", "", invoice.totals.open_balance_amount])
        sh.write_branded_footer()
        return wb

    def _invoice_list_excel(
        self,
        company: CompanyHeaderData,
        invoices: list[SalesInvoiceListItemDTO],
        page_size: PageSize,
        orientation,
    ) -> "ExcelWorkbookBuilder":
        from seeker_accounting.platform.printing.excel_builder import ExcelWorkbookBuilder

        wb = ExcelWorkbookBuilder(page_size=page_size, orientation=orientation)
        sh = wb.add_sheet("Invoice Register")
        sh.write_document_header(company, "Sales Invoice Register")
        sh.write_blank_row()
        sh.write_table_header([
            "Invoice #", "Date", "Due Date", "Customer", "Currency",
            "Subtotal", "Tax", "Total", "Open Balance", "Status", "Payment",
        ])
        for inv in invoices:
            sh.write_table_row([
                inv.invoice_number,
                self._fmt_date(inv.invoice_date),
                self._fmt_date(inv.due_date),
                inv.customer_name,
                inv.currency_code,
                inv.subtotal_amount,
                inv.tax_amount,
                inv.total_amount,
                inv.open_balance_amount,
                inv.status_code.title(),
                inv.payment_status_code.title(),
            ], numeric_columns={5, 6, 7, 8})
        sh.write_totals_row([
            "TOTALS", "", "", f"{len(invoices)} invoices", "",
            sum(i.subtotal_amount for i in invoices),
            sum(i.tax_amount for i in invoices),
            sum(i.total_amount for i in invoices),
            sum(i.open_balance_amount for i in invoices),
            "", "",
        ])
        sh.write_branded_footer()
        return wb
