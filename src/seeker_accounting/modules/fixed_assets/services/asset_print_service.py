"""Print and export service for Asset Register.

Handles all three output formats (PDF, Word, Excel) for the fixed asset listing.
List-only — no single-document detail view.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from seeker_accounting.modules.companies.dto.company_dto import CompanyDetailDTO
from seeker_accounting.modules.fixed_assets.dto.asset_dto import AssetListItemDTO
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


class AssetPrintService:
    """Renders the fixed asset register to PDF, Word, or Excel."""

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

    def print_asset_list(
        self,
        company_id: int,
        assets: list[AssetListItemDTO],
        result: PrintExportResult,
    ) -> None:
        """Render the asset register to the chosen format and path."""
        company = self._company_service.get_company(company_id)
        header = self._make_company_header(company)

        if result.format == PrintFormat.PDF:
            html = self._list_html(header, assets, result.page_size)
            self._engine.render_pdf(
                html, result.output_path,
                page_size=result.page_size,
                orientation=result.orientation,
            )
        elif result.format == PrintFormat.WORD:
            doc = self._list_word(header, assets, result.page_size, result.orientation)
            doc.save(result.output_path)
        else:
            wb = self._list_excel(header, assets, result.page_size, result.orientation)
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

    # ── HTML builder ────────────────────────────────────────────────────────────

    def _list_html(
        self,
        company: CompanyHeaderData,
        assets: list[AssetListItemDTO],
        page_size: PageSize,
    ) -> str:
        parts: list[str] = [
            build_company_header(company),
            build_document_title_block(
                "Asset Register",
                subtitle=f"{len(assets)} asset(s)",
            ),
        ]
        cols = ["Number", "Name", "Category", "Acq. Date", "Cost", "Method", "Status"]
        rows = [
            [
                a.asset_number,
                a.asset_name,
                a.asset_category_name,
                self._fmt_date(a.acquisition_date),
                self._fmt_amount(a.acquisition_cost),
                a.depreciation_method_code.replace("_", " ").title(),
                a.status_code.replace("_", " ").title(),
            ]
            for a in assets
        ]
        total_row = [f"{len(assets)} assets", "", "", "", "", "", ""]
        parts.append(build_data_table(
            cols,
            rows,
            numeric_columns={4},
            total_row=total_row,
            nowrap_columns={0, 3, 6},
            column_widths={
                0: "12%",
                1: "26%",
                2: "18%",
                3: "10%",
                4: "12%",
                5: "12%",
                6: "10%",
            },
        ))
        return wrap_html("".join(parts), page_size=page_size)

    # ── Word builder ────────────────────────────────────────────────────────────

    def _list_word(
        self,
        company: CompanyHeaderData,
        assets: list[AssetListItemDTO],
        page_size: PageSize,
        orientation,
    ) -> "WordDocumentBuilder":
        from seeker_accounting.platform.printing.word_builder import WordDocumentBuilder

        doc = WordDocumentBuilder(page_size=page_size, orientation=orientation)
        doc.add_company_header(company)
        doc.add_document_title("Asset Register", subtitle=f"{len(assets)} asset(s)")
        cols = ["Number", "Name", "Category", "Acq. Date", "Cost", "Method", "Status"]
        rows = [
            [
                a.asset_number,
                a.asset_name,
                a.asset_category_name,
                self._fmt_date(a.acquisition_date),
                self._fmt_amount(a.acquisition_cost),
                a.depreciation_method_code.replace("_", " ").title(),
                a.status_code.replace("_", " ").title(),
            ]
            for a in assets
        ]
        doc.add_data_table(
            cols, rows,
            numeric_columns={4},
            total_row=[f"{len(assets)} assets", "", "", "", "", "", ""],
        )
        return doc

    # ── Excel builder ───────────────────────────────────────────────────────────

    def _list_excel(
        self,
        company: CompanyHeaderData,
        assets: list[AssetListItemDTO],
        page_size: PageSize,
        orientation,
    ) -> "ExcelWorkbookBuilder":
        from seeker_accounting.platform.printing.excel_builder import ExcelWorkbookBuilder

        wb = ExcelWorkbookBuilder(page_size=page_size, orientation=orientation)
        sh = wb.add_sheet("Asset Register")
        sh.write_document_header(company, "Asset Register")
        sh.write_blank_row()
        sh.write_table_header(["Number", "Name", "Category", "Acq. Date", "Cost", "Method", "Status"])
        for a in assets:
            sh.write_table_row([
                a.asset_number,
                a.asset_name,
                a.asset_category_name,
                self._fmt_date(a.acquisition_date),
                a.acquisition_cost,
                a.depreciation_method_code.replace("_", " ").title(),
                a.status_code.replace("_", " ").title(),
            ], numeric_columns={4})
        sh.write_totals_row([f"{len(assets)} assets", "", "", "", "", "", ""])
        sh.write_branded_footer()
        sh.set_column_widths({1: 14, 2: 28, 3: 20, 4: 14, 5: 18, 6: 16, 7: 12})
        return wb
