"""Print and export service for Supplier Payments and Payment Register.

Handles all three output formats (PDF, Word, Excel) for:
  - Single supplier payment voucher
  - Supplier payment register list
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from seeker_accounting.modules.companies.dto.company_dto import CompanyDetailDTO
from seeker_accounting.modules.purchases.dto.supplier_payment_dto import (
    SupplierPaymentDetailDTO,
    SupplierPaymentListItemDTO,
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
    from seeker_accounting.modules.purchases.services.supplier_payment_service import SupplierPaymentService
    from seeker_accounting.platform.printing.excel_builder import ExcelWorkbookBuilder
    from seeker_accounting.platform.printing.print_engine import PrintEngine
    from seeker_accounting.platform.printing.word_builder import WordDocumentBuilder


class SupplierPaymentPrintService:
    """Renders supplier payment documents to PDF, Word, or Excel."""

    def __init__(
        self,
        print_engine: "PrintEngine",
        supplier_payment_service: "SupplierPaymentService",
        company_service: "CompanyService",
        company_logo_service: "CompanyLogoService",
    ) -> None:
        self._engine = print_engine
        self._payment_service = supplier_payment_service
        self._company_service = company_service
        self._logo_service = company_logo_service

    # ── Public API ──────────────────────────────────────────────────────────────

    def print_payment(
        self,
        company_id: int,
        payment_id: int,
        result: PrintExportResult,
    ) -> None:
        """Render a single supplier payment to the chosen format and path."""
        payment = self._payment_service.get_supplier_payment(company_id, payment_id)
        company = self._company_service.get_company(company_id)
        header = self._make_company_header(company)

        if result.format == PrintFormat.PDF:
            html = self._payment_html(header, payment, result.page_size)
            self._engine.render_pdf(
                html, result.output_path,
                page_size=result.page_size,
                orientation=result.orientation,
            )
        elif result.format == PrintFormat.WORD:
            doc = self._payment_word(header, payment, result.page_size, result.orientation)
            doc.save(result.output_path)
        else:
            wb = self._payment_excel(header, payment, result.page_size, result.orientation)
            wb.save(result.output_path)

    def print_payment_list(
        self,
        company_id: int,
        payments: list[SupplierPaymentListItemDTO],
        result: PrintExportResult,
    ) -> None:
        """Render the payment register list to the chosen format and path."""
        company = self._company_service.get_company(company_id)
        header = self._make_company_header(company)

        if result.format == PrintFormat.PDF:
            html = self._payment_list_html(header, payments, result.page_size)
            self._engine.render_pdf(
                html, result.output_path,
                page_size=result.page_size,
                orientation=result.orientation,
            )
        elif result.format == PrintFormat.WORD:
            doc = self._payment_list_word(header, payments, result.page_size, result.orientation)
            doc.save(result.output_path)
        else:
            wb = self._payment_list_excel(header, payments, result.page_size, result.orientation)
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

    def _payment_html(
        self,
        company: CompanyHeaderData,
        payment: SupplierPaymentDetailDTO,
        page_size: PageSize,
    ) -> str:
        parts: list[str] = [
            build_company_header(company),
            build_document_title_block("Supplier Payment", subtitle=payment.payment_number),
            self._paid_to_section(payment),
        ]

        if payment.allocations:
            parts.append(build_section_title("Bill Allocations"))
            alloc_cols = ["Bill #", "Bill Date", "Due Date", "Currency", "Bill Total", "Allocated"]
            alloc_rows = [
                [
                    a.purchase_bill_number,
                    self._fmt_date(a.purchase_bill_date),
                    self._fmt_date(a.purchase_bill_due_date),
                    a.bill_currency_code,
                    self._fmt_amount(a.bill_total_amount),
                    self._fmt_amount(a.allocated_amount),
                ]
                for a in payment.allocations
            ]
            total_allocated = sum(a.allocated_amount for a in payment.allocations)
            parts.append(build_data_table(
                alloc_cols, alloc_rows,
                numeric_columns={4, 5},
                total_row=["", "", "", "", "TOTAL ALLOCATED", fmt_decimal(total_allocated)],
            ))

        summary = build_summary_box([
            ("Amount Paid", self._fmt_amount(payment.amount_paid)),
            ("Allocated", self._fmt_amount(payment.allocated_amount)),
            ("Unallocated", self._fmt_amount(payment.remaining_unallocated_amount)),
        ], highlight_last=False)
        parts.append(
            '<table style="width:100%;"><tr>'
            '<td style="vertical-align:top;width:50%;"></td>'
            f'<td style="vertical-align:top;width:50%;">{summary}</td>'
            '</tr></table>'
        )

        if payment.notes:
            parts.append(build_section_title("Notes"))
            parts.append(
                f'<p style="font-size:9pt;color:#444;margin:4px 0;">{h(payment.notes)}</p>'
            )

        return wrap_html("".join(parts), page_size=page_size)

    def _paid_to_section(self, payment: SupplierPaymentDetailDTO) -> str:
        """Two-column header: Paid To (left) | Payment Details (right)."""
        left = (
            '<div style="font-size:7pt;text-transform:uppercase;font-weight:700;'
            'color:#6b7280;letter-spacing:0.5px;margin-bottom:4px;">Paid To</div>'
            f'<div style="font-weight:700;font-size:11pt;color:#1a1a1a;margin-bottom:2px;">'
            f'{h(payment.supplier_name)}</div>'
            f'<div style="font-size:9pt;color:#6b7280;">{h(payment.supplier_code)}</div>'
        )
        detail_rows = "".join(
            f'<tr>'
            f'<td style="font-size:7.5pt;color:#6b7280;text-transform:uppercase;'
            f'letter-spacing:0.3px;padding:2px 10px 2px 0;white-space:nowrap;width:40%;">{h(k)}</td>'
            f'<td style="font-size:9pt;font-weight:600;color:#1a1a1a;padding:2px 0;">{h(v)}</td>'
            f'</tr>'
            for k, v in [
                ("Payment #", payment.payment_number),
                ("Date", self._fmt_date(payment.payment_date)),
                ("Account", payment.financial_account_name),
                ("Currency", payment.currency_code),
                ("Reference", payment.reference_number or "—"),
                ("Status", payment.status_code.title()),
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

    def _payment_list_html(
        self,
        company: CompanyHeaderData,
        payments: list[SupplierPaymentListItemDTO],
        page_size: PageSize,
    ) -> str:
        parts: list[str] = [
            build_company_header(company),
            build_document_title_block(
                "Supplier Payment Register",
                subtitle=f"{len(payments)} payment(s)",
            ),
        ]
        cols = ["Payment #", "Date", "Supplier", "Account", "Currency", "Amount", "Status", "Posted At"]
        rows = [
            [
                p.payment_number,
                self._fmt_date(p.payment_date),
                p.supplier_name,
                p.financial_account_name,
                p.currency_code,
                self._fmt_amount(p.amount_paid),
                p.status_code.title(),
                p.posted_at.strftime("%d/%m/%Y") if p.posted_at else "—",
            ]
            for p in payments
        ]
        total_amount = sum(p.amount_paid for p in payments)
        total_row = [
            "TOTALS", "", f"{len(payments)} payments", "", "",
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

    def _payment_word(
        self,
        company: CompanyHeaderData,
        payment: SupplierPaymentDetailDTO,
        page_size: PageSize,
        orientation,
    ) -> "WordDocumentBuilder":
        from seeker_accounting.platform.printing.word_builder import WordDocumentBuilder

        doc = WordDocumentBuilder(page_size=page_size, orientation=orientation)
        doc.add_company_header(company)
        doc.add_document_title("Supplier Payment", subtitle=payment.payment_number)
        doc.add_key_value_grid([
            ("Supplier", payment.supplier_name),
            ("Supplier Code", payment.supplier_code),
            ("Payment #", payment.payment_number),
            ("Date", self._fmt_date(payment.payment_date)),
            ("Cash/Bank Account", payment.financial_account_name),
            ("Currency", payment.currency_code),
            ("Reference", payment.reference_number or "—"),
            ("Status", payment.status_code.title()),
        ])

        if payment.allocations:
            doc.add_section_title("Bill Allocations")
            alloc_cols = ["Bill #", "Bill Date", "Due Date", "Currency", "Bill Total", "Allocated"]
            alloc_rows = [
                [
                    a.purchase_bill_number,
                    self._fmt_date(a.purchase_bill_date),
                    self._fmt_date(a.purchase_bill_due_date),
                    a.bill_currency_code,
                    self._fmt_amount(a.bill_total_amount),
                    self._fmt_amount(a.allocated_amount),
                ]
                for a in payment.allocations
            ]
            doc.add_data_table(
                alloc_cols, alloc_rows,
                numeric_columns={4, 5},
                total_row=["", "", "", "", "TOTAL",
                           fmt_decimal(sum(a.allocated_amount for a in payment.allocations))],
            )

        doc.add_summary_pairs([
            ("Amount Paid", self._fmt_amount(payment.amount_paid)),
            ("Allocated", self._fmt_amount(payment.allocated_amount)),
            ("Unallocated", self._fmt_amount(payment.remaining_unallocated_amount)),
        ])

        if payment.notes:
            doc.add_section_title("Notes")
            doc.add_paragraph(payment.notes, italic=True)

        return doc

    def _payment_list_word(
        self,
        company: CompanyHeaderData,
        payments: list[SupplierPaymentListItemDTO],
        page_size: PageSize,
        orientation,
    ) -> "WordDocumentBuilder":
        from seeker_accounting.platform.printing.word_builder import WordDocumentBuilder

        doc = WordDocumentBuilder(page_size=page_size, orientation=orientation)
        doc.add_company_header(company)
        doc.add_document_title("Supplier Payment Register", subtitle=f"{len(payments)} payment(s)")
        cols = ["Payment #", "Date", "Supplier", "Account", "Currency", "Amount", "Status"]
        rows = [
            [
                p.payment_number,
                self._fmt_date(p.payment_date),
                p.supplier_name,
                p.financial_account_name,
                p.currency_code,
                self._fmt_amount(p.amount_paid),
                p.status_code.title(),
            ]
            for p in payments
        ]
        doc.add_data_table(
            cols, rows,
            numeric_columns={5},
            total_row=[
                "TOTALS", "", f"{len(payments)} payments", "", "",
                fmt_decimal(sum(p.amount_paid for p in payments)),
                "",
            ],
        )
        return doc

    # ── Excel builders ──────────────────────────────────────────────────────────

    def _payment_excel(
        self,
        company: CompanyHeaderData,
        payment: SupplierPaymentDetailDTO,
        page_size: PageSize,
        orientation,
    ) -> "ExcelWorkbookBuilder":
        from seeker_accounting.platform.printing.excel_builder import ExcelWorkbookBuilder

        wb = ExcelWorkbookBuilder(page_size=page_size, orientation=orientation)
        sh = wb.add_sheet("Payment")
        sh.write_document_header(company, f"Supplier Payment — {payment.payment_number}")
        sh.write_key_value_pairs([
            ("Supplier", payment.supplier_name),
            ("Date", self._fmt_date(payment.payment_date)),
            ("Cash/Bank Account", payment.financial_account_name),
            ("Currency", payment.currency_code),
            ("Reference", payment.reference_number or "—"),
            ("Status", payment.status_code.title()),
        ])
        sh.write_blank_row()

        if payment.allocations:
            sh.write_table_header(["Bill #", "Bill Date", "Due Date", "Currency", "Bill Total", "Allocated"])
            for a in payment.allocations:
                sh.write_table_row([
                    a.purchase_bill_number,
                    self._fmt_date(a.purchase_bill_date),
                    self._fmt_date(a.purchase_bill_due_date),
                    a.bill_currency_code,
                    a.bill_total_amount,
                    a.allocated_amount,
                ], numeric_columns={4, 5})
            sh.write_totals_row([
                "", "", "", "", "Total Allocated",
                sum(a.allocated_amount for a in payment.allocations),
            ])
            sh.write_blank_row()

        sh.write_totals_row(["Amount Paid", "", "", "", "", payment.amount_paid])
        sh.write_totals_row(["Allocated", "", "", "", "", payment.allocated_amount])
        sh.write_totals_row(["Unallocated", "", "", "", "", payment.remaining_unallocated_amount])
        sh.write_branded_footer()
        return wb

    def _payment_list_excel(
        self,
        company: CompanyHeaderData,
        payments: list[SupplierPaymentListItemDTO],
        page_size: PageSize,
        orientation,
    ) -> "ExcelWorkbookBuilder":
        from seeker_accounting.platform.printing.excel_builder import ExcelWorkbookBuilder

        wb = ExcelWorkbookBuilder(page_size=page_size, orientation=orientation)
        sh = wb.add_sheet("Payment Register")
        sh.write_document_header(company, "Supplier Payment Register")
        sh.write_blank_row()
        sh.write_table_header(["Payment #", "Date", "Supplier", "Account", "Currency", "Amount", "Status", "Posted At"])
        for p in payments:
            sh.write_table_row([
                p.payment_number,
                self._fmt_date(p.payment_date),
                p.supplier_name,
                p.financial_account_name,
                p.currency_code,
                p.amount_paid,
                p.status_code.title(),
                p.posted_at.strftime("%d/%m/%Y") if p.posted_at else "",
            ], numeric_columns={5})
        sh.write_totals_row([
            "TOTALS", "", f"{len(payments)} payments", "", "",
            sum(p.amount_paid for p in payments),
            "", "",
        ])
        sh.write_branded_footer()
        return wb
