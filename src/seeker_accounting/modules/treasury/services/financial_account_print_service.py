"""Print and export service for Financial Account Register.

Handles all three output formats (PDF, Word, Excel) for the financial account listing.
List-only — no single-document detail view.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from seeker_accounting.modules.companies.dto.company_dto import CompanyDetailDTO
from seeker_accounting.modules.treasury.dto.financial_account_dto import FinancialAccountListItemDTO
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


class FinancialAccountPrintService:
    """Renders the financial account register to PDF, Word, or Excel."""

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

    def print_account_list(
        self,
        company_id: int,
        accounts: list[FinancialAccountListItemDTO],
        result: PrintExportResult,
    ) -> None:
        """Render the financial account register to the chosen format and path."""
        company = self._company_service.get_company(company_id)
        header = self._make_company_header(company)

        if result.format == PrintFormat.PDF:
            html = self._list_html(header, accounts, result.page_size)
            self._engine.render_pdf(
                html, result.output_path,
                page_size=result.page_size,
                orientation=result.orientation,
            )
        elif result.format == PrintFormat.WORD:
            doc = self._list_word(header, accounts, result.page_size, result.orientation)
            doc.save(result.output_path)
        else:
            wb = self._list_excel(header, accounts, result.page_size, result.orientation)
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

    # ── HTML builder ────────────────────────────────────────────────────────────

    def _list_html(
        self,
        company: CompanyHeaderData,
        accounts: list[FinancialAccountListItemDTO],
        page_size: PageSize,
    ) -> str:
        parts: list[str] = [
            build_company_header(company),
            build_document_title_block(
                "Financial Account Register",
                subtitle=f"{len(accounts)} account(s)",
            ),
        ]
        cols = ["Code", "Name", "Type", "GL Account", "Currency", "Active"]
        rows = [
            [
                a.account_code,
                a.name,
                a.financial_account_type_code.replace("_", " ").title(),
                f"{a.gl_account_code} — {a.gl_account_name}",
                a.currency_code,
                "Yes" if a.is_active else "No",
            ]
            for a in accounts
        ]
        total_row = [f"{len(accounts)} accounts", "", "", "", "", ""]
        parts.append(build_data_table(
            cols,
            rows,
            total_row=total_row,
            nowrap_columns={0, 4, 5},
            column_widths={
                0: "12%",
                1: "22%",
                2: "16%",
                3: "30%",
                4: "10%",
                5: "10%",
            },
        ))
        return wrap_html("".join(parts), page_size=page_size)

    # ── Word builder ────────────────────────────────────────────────────────────

    def _list_word(
        self,
        company: CompanyHeaderData,
        accounts: list[FinancialAccountListItemDTO],
        page_size: PageSize,
        orientation,
    ) -> "WordDocumentBuilder":
        from seeker_accounting.platform.printing.word_builder import WordDocumentBuilder

        doc = WordDocumentBuilder(page_size=page_size, orientation=orientation)
        doc.add_company_header(company)
        doc.add_document_title("Financial Account Register", subtitle=f"{len(accounts)} account(s)")
        cols = ["Code", "Name", "Type", "GL Account", "Currency", "Active"]
        rows = [
            [
                a.account_code,
                a.name,
                a.financial_account_type_code.replace("_", " ").title(),
                f"{a.gl_account_code} — {a.gl_account_name}",
                a.currency_code,
                "Yes" if a.is_active else "No",
            ]
            for a in accounts
        ]
        doc.add_data_table(
            cols, rows,
            total_row=[f"{len(accounts)} accounts", "", "", "", "", ""],
        )
        return doc

    # ── Excel builder ───────────────────────────────────────────────────────────

    def _list_excel(
        self,
        company: CompanyHeaderData,
        accounts: list[FinancialAccountListItemDTO],
        page_size: PageSize,
        orientation,
    ) -> "ExcelWorkbookBuilder":
        from seeker_accounting.platform.printing.excel_builder import ExcelWorkbookBuilder

        wb = ExcelWorkbookBuilder(page_size=page_size, orientation=orientation)
        sh = wb.add_sheet("Financial Accounts")
        sh.write_document_header(company, "Financial Account Register")
        sh.write_blank_row()
        sh.write_table_header(["Code", "Name", "Type", "GL Account", "Currency", "Active"])
        for a in accounts:
            sh.write_table_row([
                a.account_code,
                a.name,
                a.financial_account_type_code.replace("_", " ").title(),
                f"{a.gl_account_code} — {a.gl_account_name}",
                a.currency_code,
                "Yes" if a.is_active else "No",
            ])
        sh.write_totals_row([f"{len(accounts)} accounts", "", "", "", "", ""])
        sh.write_branded_footer()
        sh.set_column_widths({1: 14, 2: 28, 3: 16, 4: 30, 5: 10, 6: 10})
        return wb
