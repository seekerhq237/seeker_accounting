"""Print and export service for Customer Register.

Handles all three output formats (PDF, Word, Excel) for the customer listing.
List-only — no single-document detail view.
"""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from seeker_accounting.modules.companies.dto.company_dto import CompanyDetailDTO
from seeker_accounting.modules.customers.dto.customer_dto import CustomerListItemDTO
from seeker_accounting.platform.printing.html_builder import (
    build_company_header,
    build_data_table,
    build_document_title_block,
    fmt_decimal,
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


class CustomerPrintService:
    """Renders the customer register to PDF, Word, or Excel."""

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

    def print_customer_list(
        self,
        company_id: int,
        customers: list[CustomerListItemDTO],
        result: PrintExportResult,
    ) -> None:
        """Render the customer register to the chosen format and path."""
        company = self._company_service.get_company(company_id)
        header = self._make_company_header(company)

        if result.format == PrintFormat.PDF:
            html = self._list_html(header, customers, result.page_size)
            self._engine.render_pdf(
                html, result.output_path,
                page_size=result.page_size,
                orientation=result.orientation,
            )
        elif result.format == PrintFormat.WORD:
            doc = self._list_word(header, customers, result.page_size, result.orientation)
            doc.save(result.output_path)
        else:
            wb = self._list_excel(header, customers, result.page_size, result.orientation)
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

    @staticmethod
    def _fmt_amount(v: Decimal | None) -> str:
        return fmt_decimal(v) if v is not None else "—"

    # ── HTML builder ────────────────────────────────────────────────────────────

    def _list_html(
        self,
        company: CompanyHeaderData,
        customers: list[CustomerListItemDTO],
        page_size: PageSize,
    ) -> str:
        parts: list[str] = [
            build_company_header(company),
            build_document_title_block(
                "Customer Register",
                subtitle=f"{len(customers)} customer(s)",
            ),
        ]
        cols = ["Code", "Name", "Group", "Payment Terms", "Country", "Credit Limit", "Active"]
        rows = [
            [
                c.customer_code,
                c.display_name,
                c.customer_group_name or "",
                c.payment_term_name or "",
                c.country_code or "",
                self._fmt_amount(c.credit_limit_amount),
                "Yes" if c.is_active else "No",
            ]
            for c in customers
        ]
        total_row = [f"{len(customers)} customers", "", "", "", "", "", ""]
        parts.append(build_data_table(
            cols,
            rows,
            numeric_columns={5},
            total_row=total_row,
            nowrap_columns={0, 4, 6},
            column_widths={
                0: "12%",
                1: "24%",
                2: "14%",
                3: "18%",
                4: "10%",
                5: "12%",
                6: "10%",
            },
        ))
        return wrap_html("".join(parts), page_size=page_size)

    # ── Word builder ────────────────────────────────────────────────────────────

    def _list_word(
        self,
        company: CompanyHeaderData,
        customers: list[CustomerListItemDTO],
        page_size: PageSize,
        orientation,
    ) -> "WordDocumentBuilder":
        from seeker_accounting.platform.printing.word_builder import WordDocumentBuilder

        doc = WordDocumentBuilder(page_size=page_size, orientation=orientation)
        doc.add_company_header(company)
        doc.add_document_title("Customer Register", subtitle=f"{len(customers)} customer(s)")
        cols = ["Code", "Name", "Group", "Payment Terms", "Country", "Credit Limit", "Active"]
        rows = [
            [
                c.customer_code,
                c.display_name,
                c.customer_group_name or "",
                c.payment_term_name or "",
                c.country_code or "",
                self._fmt_amount(c.credit_limit_amount),
                "Yes" if c.is_active else "No",
            ]
            for c in customers
        ]
        doc.add_data_table(
            cols, rows,
            numeric_columns={5},
            total_row=[f"{len(customers)} customers", "", "", "", "", "", ""],
        )
        return doc

    # ── Excel builder ───────────────────────────────────────────────────────────

    def _list_excel(
        self,
        company: CompanyHeaderData,
        customers: list[CustomerListItemDTO],
        page_size: PageSize,
        orientation,
    ) -> "ExcelWorkbookBuilder":
        from seeker_accounting.platform.printing.excel_builder import ExcelWorkbookBuilder

        wb = ExcelWorkbookBuilder(page_size=page_size, orientation=orientation)
        sh = wb.add_sheet("Customer Register")
        sh.write_document_header(company, "Customer Register")
        sh.write_blank_row()
        sh.write_table_header(["Code", "Name", "Group", "Payment Terms", "Country", "Credit Limit", "Active"])
        for c in customers:
            sh.write_table_row([
                c.customer_code,
                c.display_name,
                c.customer_group_name or "",
                c.payment_term_name or "",
                c.country_code or "",
                c.credit_limit_amount if c.credit_limit_amount is not None else "",
                "Yes" if c.is_active else "No",
            ], numeric_columns={5})
        sh.write_totals_row([f"{len(customers)} customers", "", "", "", "", "", ""])
        sh.write_branded_footer()
        sh.set_column_widths({1: 14, 2: 30, 3: 18, 4: 18, 5: 10, 6: 16, 7: 10})
        return wb
