"""Print and export service for Purchase Bills and Bill Register.

Handles all three output formats (PDF, Word, Excel) for:
  - Single purchase bill detail document
  - Purchase bill register list
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from seeker_accounting.modules.companies.dto.company_dto import CompanyDetailDTO
from seeker_accounting.modules.purchases.dto.purchase_bill_dto import (
    PurchaseBillDetailDTO,
    PurchaseBillListItemDTO,
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
    from seeker_accounting.modules.purchases.services.purchase_bill_service import PurchaseBillService
    from seeker_accounting.platform.printing.excel_builder import ExcelWorkbookBuilder
    from seeker_accounting.platform.printing.print_engine import PrintEngine
    from seeker_accounting.platform.printing.word_builder import WordDocumentBuilder


class PurchaseBillPrintService:
    """Renders purchase bill documents to PDF, Word, or Excel."""

    def __init__(
        self,
        print_engine: "PrintEngine",
        purchase_bill_service: "PurchaseBillService",
        company_service: "CompanyService",
        company_logo_service: "CompanyLogoService",
    ) -> None:
        self._engine = print_engine
        self._bill_service = purchase_bill_service
        self._company_service = company_service
        self._logo_service = company_logo_service

    # ── Public API ──────────────────────────────────────────────────────────────

    def print_bill(
        self,
        company_id: int,
        bill_id: int,
        result: PrintExportResult,
    ) -> None:
        """Render a single purchase bill to the chosen format and path."""
        bill = self._bill_service.get_purchase_bill(company_id, bill_id)
        company = self._company_service.get_company(company_id)
        header = self._make_company_header(company)

        if result.format == PrintFormat.PDF:
            html = self._bill_html(header, bill, result.page_size)
            self._engine.render_pdf(
                html, result.output_path,
                page_size=result.page_size,
                orientation=result.orientation,
            )
        elif result.format == PrintFormat.WORD:
            doc = self._bill_word(header, bill, result.page_size, result.orientation)
            doc.save(result.output_path)
        else:
            wb = self._bill_excel(header, bill, result.page_size, result.orientation)
            wb.save(result.output_path)

    def print_bill_list(
        self,
        company_id: int,
        bills: list[PurchaseBillListItemDTO],
        result: PrintExportResult,
    ) -> None:
        """Render the bill register (list) to the chosen format and path."""
        company = self._company_service.get_company(company_id)
        header = self._make_company_header(company)

        if result.format == PrintFormat.PDF:
            html = self._bill_list_html(header, bills, result.page_size)
            self._engine.render_pdf(
                html, result.output_path,
                page_size=result.page_size,
                orientation=result.orientation,
            )
        elif result.format == PrintFormat.WORD:
            doc = self._bill_list_word(header, bills, result.page_size, result.orientation)
            doc.save(result.output_path)
        else:
            wb = self._bill_list_excel(header, bills, result.page_size, result.orientation)
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

    def _bill_html(
        self,
        company: CompanyHeaderData,
        bill: PurchaseBillDetailDTO,
        page_size: PageSize,
    ) -> str:
        parts: list[str] = [
            build_company_header(company),
            build_document_title_block("Purchase Bill", subtitle=bill.bill_number),
            self._supplier_section(bill),
        ]

        parts.append(build_section_title("Line Items"))
        line_cols = ["#", "Description", "Account", "Qty", "Unit Cost", "Tax", "Subtotal", "Tax Amt", "Total"]
        line_rows = [
            [
                str(ln.line_number),
                ln.description,
                f"{ln.expense_account_code} — {ln.expense_account_name}",
                fmt_decimal(ln.quantity, 2) if ln.quantity else "—",
                self._fmt_amount(ln.unit_cost),
                ln.tax_code_code or "—",
                self._fmt_amount(ln.line_subtotal_amount),
                self._fmt_amount(ln.line_tax_amount),
                self._fmt_amount(ln.line_total_amount),
            ]
            for ln in bill.lines
        ]
        trailing_total = ["", "", "", "", "", "", "", "TOTAL", self._fmt_amount(bill.totals.total_amount)]
        parts.append(build_data_table(
            line_cols, line_rows,
            numeric_columns={3, 4, 6, 7, 8},
            total_row=trailing_total,
        ))

        summary = build_summary_box([
            ("Subtotal", self._fmt_amount(bill.totals.subtotal_amount)),
            ("Tax", self._fmt_amount(bill.totals.tax_amount)),
            ("Grand Total", self._fmt_amount(bill.totals.total_amount)),
            ("Allocated", self._fmt_amount(bill.totals.allocated_amount)),
            ("Open Balance", self._fmt_amount(bill.totals.open_balance_amount)),
        ], highlight_last=False)
        parts.append(
            '<table style="width:100%;"><tr>'
            '<td style="vertical-align:top;width:50%;"></td>'
            f'<td style="vertical-align:top;width:50%;">{summary}</td>'
            '</tr></table>'
        )

        if bill.notes:
            parts.append(build_section_title("Notes"))
            parts.append(
                f'<p style="font-size:9pt;color:#444;margin:4px 0;">{h(bill.notes)}</p>'
            )

        return wrap_html("".join(parts), page_size=page_size)

    def _supplier_section(self, bill: PurchaseBillDetailDTO) -> str:
        """Two-column header: Supplier (left) | Bill Details (right)."""
        pay_label = {
            "unpaid": "Unpaid",
            "partial": "Partially Paid",
            "paid": "Paid",
        }.get(bill.payment_status_code, bill.payment_status_code.title())

        left = (
            '<div style="font-size:7pt;text-transform:uppercase;font-weight:700;'
            'color:#6b7280;letter-spacing:0.5px;margin-bottom:4px;">Supplier</div>'
            f'<div style="font-weight:700;font-size:11pt;color:#1a1a1a;margin-bottom:2px;">'
            f'{h(bill.supplier_name)}</div>'
            f'<div style="font-size:9pt;color:#6b7280;">{h(bill.supplier_code)}</div>'
        )
        detail_rows = "".join(
            f'<tr>'
            f'<td style="font-size:7.5pt;color:#6b7280;text-transform:uppercase;'
            f'letter-spacing:0.3px;padding:2px 10px 2px 0;white-space:nowrap;width:38%;">{h(k)}</td>'
            f'<td style="font-size:9pt;font-weight:600;color:#1a1a1a;padding:2px 0;">{h(v)}</td>'
            f'</tr>'
            for k, v in [
                ("Bill #", bill.bill_number),
                ("Date", self._fmt_date(bill.bill_date)),
                ("Due Date", self._fmt_date(bill.due_date)),
                ("Currency", bill.currency_code),
                ("Supplier Ref", bill.supplier_bill_reference or "—"),
                ("Status", bill.status_code.title()),
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

    def _bill_list_html(
        self,
        company: CompanyHeaderData,
        bills: list[PurchaseBillListItemDTO],
        page_size: PageSize,
    ) -> str:
        parts: list[str] = [
            build_company_header(company),
            build_document_title_block(
                "Purchase Bill Register",
                subtitle=f"{len(bills)} bill(s)",
            ),
        ]
        cols = [
            "Bill #", "Date", "Due Date", "Supplier", "Curr.",
            "Subtotal", "Tax", "Total", "Open Balance", "Status", "Payment",
        ]
        rows = [
            [
                b.bill_number,
                self._fmt_date(b.bill_date),
                self._fmt_date(b.due_date),
                b.supplier_name,
                b.currency_code,
                self._fmt_amount(b.subtotal_amount),
                self._fmt_amount(b.tax_amount),
                self._fmt_amount(b.total_amount),
                self._fmt_amount(b.open_balance_amount),
                b.status_code.title(),
                b.payment_status_code.title(),
            ]
            for b in bills
        ]
        total_subtotal = sum(b.subtotal_amount for b in bills)
        total_tax = sum(b.tax_amount for b in bills)
        total_total = sum(b.total_amount for b in bills)
        total_open = sum(b.open_balance_amount for b in bills)
        total_row = [
            "TOTALS", "", "", f"{len(bills)} bills", "",
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

    def _bill_word(
        self,
        company: CompanyHeaderData,
        bill: PurchaseBillDetailDTO,
        page_size: PageSize,
        orientation,
    ) -> "WordDocumentBuilder":
        from seeker_accounting.platform.printing.word_builder import WordDocumentBuilder

        pay_label = {"unpaid": "Unpaid", "partial": "Partially Paid", "paid": "Paid"}.get(
            bill.payment_status_code, bill.payment_status_code.title()
        )
        doc = WordDocumentBuilder(page_size=page_size, orientation=orientation)
        doc.add_company_header(company)
        doc.add_document_title("Purchase Bill", subtitle=bill.bill_number)
        doc.add_key_value_grid([
            ("Supplier", bill.supplier_name),
            ("Supplier Code", bill.supplier_code),
            ("Bill #", bill.bill_number),
            ("Bill Date", self._fmt_date(bill.bill_date)),
            ("Due Date", self._fmt_date(bill.due_date)),
            ("Currency", bill.currency_code),
            ("Supplier Ref", bill.supplier_bill_reference or "—"),
            ("Status", bill.status_code.title()),
            ("Payment", pay_label),
        ])
        doc.add_section_title("Line Items")
        line_cols = ["#", "Description", "Account", "Qty", "Unit Cost", "Tax", "Subtotal", "Tax Amt", "Total"]
        line_rows = [
            [
                str(ln.line_number),
                ln.description,
                ln.expense_account_code,
                fmt_decimal(ln.quantity, 2) if ln.quantity else "—",
                self._fmt_amount(ln.unit_cost),
                ln.tax_code_code or "—",
                self._fmt_amount(ln.line_subtotal_amount),
                self._fmt_amount(ln.line_tax_amount),
                self._fmt_amount(ln.line_total_amount),
            ]
            for ln in bill.lines
        ]
        doc.add_data_table(
            line_cols, line_rows,
            numeric_columns={3, 4, 6, 7, 8},
            total_row=["", "", "", "", "", "", "", "TOTAL", self._fmt_amount(bill.totals.total_amount)],
        )
        doc.add_summary_pairs([
            ("Subtotal", self._fmt_amount(bill.totals.subtotal_amount)),
            ("Tax Amount", self._fmt_amount(bill.totals.tax_amount)),
            ("Grand Total", self._fmt_amount(bill.totals.total_amount)),
            ("Allocated", self._fmt_amount(bill.totals.allocated_amount)),
            ("Open Balance", self._fmt_amount(bill.totals.open_balance_amount)),
        ])
        if bill.notes:
            doc.add_section_title("Notes")
            doc.add_paragraph(bill.notes, italic=True)
        return doc

    def _bill_list_word(
        self,
        company: CompanyHeaderData,
        bills: list[PurchaseBillListItemDTO],
        page_size: PageSize,
        orientation,
    ) -> "WordDocumentBuilder":
        from seeker_accounting.platform.printing.word_builder import WordDocumentBuilder

        doc = WordDocumentBuilder(page_size=page_size, orientation=orientation)
        doc.add_company_header(company)
        doc.add_document_title("Purchase Bill Register", subtitle=f"{len(bills)} bill(s)")
        cols = [
            "Bill #", "Date", "Due Date", "Supplier", "Curr.",
            "Subtotal", "Tax", "Total", "Open Bal.", "Status",
        ]
        rows = [
            [
                b.bill_number,
                self._fmt_date(b.bill_date),
                self._fmt_date(b.due_date),
                b.supplier_name,
                b.currency_code,
                self._fmt_amount(b.subtotal_amount),
                self._fmt_amount(b.tax_amount),
                self._fmt_amount(b.total_amount),
                self._fmt_amount(b.open_balance_amount),
                b.status_code.title(),
            ]
            for b in bills
        ]
        doc.add_data_table(
            cols, rows,
            numeric_columns={5, 6, 7, 8},
            total_row=[
                "TOTALS", "", "", "", "",
                fmt_decimal(sum(b.subtotal_amount for b in bills)),
                fmt_decimal(sum(b.tax_amount for b in bills)),
                fmt_decimal(sum(b.total_amount for b in bills)),
                fmt_decimal(sum(b.open_balance_amount for b in bills)),
                "",
            ],
        )
        return doc

    # ── Excel builders ──────────────────────────────────────────────────────────

    def _bill_excel(
        self,
        company: CompanyHeaderData,
        bill: PurchaseBillDetailDTO,
        page_size: PageSize,
        orientation,
    ) -> "ExcelWorkbookBuilder":
        from seeker_accounting.platform.printing.excel_builder import ExcelWorkbookBuilder

        pay_label = {"unpaid": "Unpaid", "partial": "Partially Paid", "paid": "Paid"}.get(
            bill.payment_status_code, bill.payment_status_code.title()
        )
        wb = ExcelWorkbookBuilder(page_size=page_size, orientation=orientation)
        sh = wb.add_sheet("Bill")
        sh.write_document_header(company, f"Purchase Bill — {bill.bill_number}")
        sh.write_key_value_pairs([
            ("Supplier", bill.supplier_name),
            ("Bill Date", self._fmt_date(bill.bill_date)),
            ("Due Date", self._fmt_date(bill.due_date)),
            ("Currency", bill.currency_code),
            ("Supplier Ref", bill.supplier_bill_reference or "—"),
            ("Status", bill.status_code.title()),
            ("Payment", pay_label),
        ])
        sh.write_blank_row()
        sh.write_table_header(["#", "Description", "Account", "Qty", "Unit Cost", "Tax", "Subtotal", "Tax Amt", "Total"])
        for ln in bill.lines:
            sh.write_table_row([
                ln.line_number,
                ln.description,
                ln.expense_account_code,
                ln.quantity or "",
                ln.unit_cost,
                ln.tax_code_code or "",
                ln.line_subtotal_amount,
                ln.line_tax_amount,
                ln.line_total_amount,
            ], numeric_columns={3, 4, 6, 7, 8})
        sh.write_totals_row(["", "", "", "", "", "", "Subtotal", "", bill.totals.subtotal_amount])
        sh.write_totals_row(["", "", "", "", "", "", "Tax", "", bill.totals.tax_amount])
        sh.write_totals_row(["", "", "", "", "", "", "Grand Total", "", bill.totals.total_amount])
        sh.write_totals_row(["", "", "", "", "", "", "Allocated", "", bill.totals.allocated_amount])
        sh.write_totals_row(["", "", "", "", "", "", "Open Balance", "", bill.totals.open_balance_amount])
        sh.write_branded_footer()
        return wb

    def _bill_list_excel(
        self,
        company: CompanyHeaderData,
        bills: list[PurchaseBillListItemDTO],
        page_size: PageSize,
        orientation,
    ) -> "ExcelWorkbookBuilder":
        from seeker_accounting.platform.printing.excel_builder import ExcelWorkbookBuilder

        wb = ExcelWorkbookBuilder(page_size=page_size, orientation=orientation)
        sh = wb.add_sheet("Bill Register")
        sh.write_document_header(company, "Purchase Bill Register")
        sh.write_blank_row()
        sh.write_table_header([
            "Bill #", "Date", "Due Date", "Supplier", "Currency",
            "Subtotal", "Tax", "Total", "Open Balance", "Status", "Payment",
        ])
        for b in bills:
            sh.write_table_row([
                b.bill_number,
                self._fmt_date(b.bill_date),
                self._fmt_date(b.due_date),
                b.supplier_name,
                b.currency_code,
                b.subtotal_amount,
                b.tax_amount,
                b.total_amount,
                b.open_balance_amount,
                b.status_code.title(),
                b.payment_status_code.title(),
            ], numeric_columns={5, 6, 7, 8})
        sh.write_totals_row([
            "TOTALS", "", "", f"{len(bills)} bills", "",
            sum(b.subtotal_amount for b in bills),
            sum(b.tax_amount for b in bills),
            sum(b.total_amount for b in bills),
            sum(b.open_balance_amount for b in bills),
            "", "",
        ])
        sh.write_branded_footer()
        return wb
