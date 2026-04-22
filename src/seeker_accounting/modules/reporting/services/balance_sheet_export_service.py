"""Export service for Balance Sheet reports (IAS and OHADA).

Each balance-sheet variant produces its own intentional, statement-specific
section layout for the renderers:

* **IAS** — one section, 3-column (Ref | Description | Amount), hierarchical
  with sections / groups / lines / formulas.
* **OHADA** — two sections:
    * Assets (Ref | Description | Gross | Amort./Deprec. | Net) — 5 columns
    * Liabilities & Equity (Ref | Description | Amount) — 3 columns
  matching the OHADA SYSCOHADA Bilan presentation.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from seeker_accounting.modules.companies.services.company_logo_service import CompanyLogoService
from seeker_accounting.modules.companies.services.company_service import CompanyService
from seeker_accounting.modules.reporting.dto.ias_balance_sheet_dto import (
    IasBalanceSheetLineDTO,
    IasBalanceSheetReportDTO,
)
from seeker_accounting.modules.reporting.dto.ohada_balance_sheet_dto import (
    OhadaBalanceSheetLineDTO,
    OhadaBalanceSheetReportDTO,
)
from seeker_accounting.modules.reporting.export.excel_renderer import (
    FinancialStatementExcelRenderer,
)
from seeker_accounting.modules.reporting.export.export_models import (
    StatementCompanyInfo,
    StatementExportFormat,
    StatementExportResult,
    StatementExportRow,
    StatementTableSection,
)
from seeker_accounting.modules.reporting.export.pdf_renderer import (
    FinancialStatementPdfRenderer,
)
from seeker_accounting.modules.reporting.export.word_renderer import (
    FinancialStatementWordRenderer,
)

_ZERO = Decimal("0.00")


class BalanceSheetExportService:
    """Exports IAS and OHADA balance sheets to PDF / Word / Excel."""

    def __init__(
        self,
        company_service: CompanyService,
        company_logo_service: CompanyLogoService,
    ) -> None:
        self._company_service = company_service
        self._company_logo_service = company_logo_service
        self._pdf = FinancialStatementPdfRenderer()
        self._word = FinancialStatementWordRenderer()
        self._excel = FinancialStatementExcelRenderer()

    # ==================================================================
    # IAS Balance Sheet
    # ==================================================================

    def export_ias(
        self,
        report: IasBalanceSheetReportDTO,
        company_id: int,
        result: StatementExportResult,
    ) -> None:
        company_info = self._build_company_info(company_id)
        section = self._ias_section(report)
        summary = self._ias_summary(report)
        date_label = (
            f"As at {report.statement_date.strftime('%d %B %Y')}"
            if report.statement_date
            else "As at unspecified date"
        )

        kwargs = dict(
            title="Statement of Financial Position",
            subtitle=report.template_title,
            date_label=date_label,
            company=company_info,
            sections=[section],
            summary_pairs=summary,
            output_path=result.output_path,
            page_size=result.page_size,
            orientation=result.orientation,
        )

        self._dispatch(result.format, kwargs)

    def _ias_section(self, report: IasBalanceSheetReportDTO) -> StatementTableSection:
        """Single table section for the IAS balance sheet."""
        rows: list[StatementExportRow] = []
        for line in report.lines:
            rows.append(
                StatementExportRow(
                    row_kind=line.row_kind_code,
                    indent_level=line.indent_level,
                    ref_code=line.code,
                    label=line.label,
                    amounts=(line.amount,),
                )
            )
        return StatementTableSection(
            heading=None,
            column_headers=("Ref", "Description", "Amount"),
            rows=tuple(rows),
            column_widths=(10.0, 55.0, 20.0),
        )

    def _ias_summary(self, report: IasBalanceSheetReportDTO) -> list[tuple[str, str]]:
        return [
            ("Total Assets", self._fmt(report.total_assets)),
            ("Total Equity & Liabilities", self._fmt(report.total_equity_and_liabilities)),
            ("Difference", self._fmt(report.balance_difference)),
        ]

    # ==================================================================
    # OHADA Balance Sheet — two separate sections
    # ==================================================================

    def export_ohada(
        self,
        report: OhadaBalanceSheetReportDTO,
        company_id: int,
        result: StatementExportResult,
    ) -> None:
        company_info = self._build_company_info(company_id)
        asset_section = self._ohada_asset_section(report)
        liability_section = self._ohada_liability_section(report)
        summary = self._ohada_summary(report)
        date_label = (
            f"As at {report.statement_date.strftime('%d %B %Y')}"
            if report.statement_date
            else "As at unspecified date"
        )

        kwargs = dict(
            title="Bilan — OHADA SYSCOHADA",
            subtitle=report.template_title,
            date_label=date_label,
            company=company_info,
            sections=[asset_section, liability_section],
            summary_pairs=summary,
            output_path=result.output_path,
            page_size=result.page_size,
            orientation=result.orientation,
        )

        self._dispatch(result.format, kwargs)

    def _ohada_asset_section(
        self, report: OhadaBalanceSheetReportDTO,
    ) -> StatementTableSection:
        """Assets table: 5 columns (Ref, Description, Gross, Amort/Deprec., Net)."""
        rows: list[StatementExportRow] = []
        for line in report.asset_lines:
            rows.append(
                StatementExportRow(
                    row_kind=line.row_kind_code,
                    indent_level=0,
                    ref_code=line.reference_code or "",
                    label=line.label,
                    amounts=(line.gross_amount, line.contra_amount, line.net_amount),
                )
            )
        return StatementTableSection(
            heading="ACTIF (Assets)",
            column_headers=("Ref", "Description", "Brut (Gross)", "Amort./Déprec.", "Net"),
            rows=tuple(rows),
            column_widths=(8.0, 46.0, 16.0, 16.0, 16.0),
        )

    def _ohada_liability_section(
        self, report: OhadaBalanceSheetReportDTO,
    ) -> StatementTableSection:
        """Liabilities & Equity table: 3 columns (Ref, Description, Amount)."""
        rows: list[StatementExportRow] = []
        for line in report.liability_lines:
            rows.append(
                StatementExportRow(
                    row_kind=line.row_kind_code,
                    indent_level=0,
                    ref_code=line.reference_code or "",
                    label=line.label,
                    amounts=(line.net_amount,),
                )
            )
        return StatementTableSection(
            heading="PASSIF (Liabilities & Equity)",
            column_headers=("Ref", "Description", "Montant (Amount)"),
            rows=tuple(rows),
            column_widths=(8.0, 55.0, 20.0),
        )

    def _ohada_summary(self, report: OhadaBalanceSheetReportDTO) -> list[tuple[str, str]]:
        return [
            ("Total Assets (Net)", self._fmt(report.total_assets)),
            ("Total Liabilities & Equity", self._fmt(report.total_liabilities_and_equity)),
            ("Difference", self._fmt(report.balance_difference)),
        ]

    # ==================================================================
    # Helpers
    # ==================================================================

    def _dispatch(self, fmt: StatementExportFormat, kwargs: dict) -> None:
        if fmt == StatementExportFormat.PDF:
            self._pdf.render(**kwargs)
        elif fmt == StatementExportFormat.WORD:
            self._word.render(**kwargs)
        elif fmt == StatementExportFormat.EXCEL:
            self._excel.render(**kwargs)

    def _build_company_info(self, company_id: int) -> StatementCompanyInfo:
        company = self._company_service.get_company(company_id)
        logo_path: str | None = None
        if company.logo_storage_path:
            resolved = self._company_logo_service.resolve_logo_path(company.logo_storage_path)
            if resolved:
                logo_path = str(resolved)
        return StatementCompanyInfo(
            name=company.display_name,
            legal_name=company.legal_name,
            address_line_1=company.address_line_1,
            address_line_2=company.address_line_2,
            city=company.city,
            region=company.region,
            country_code=company.country_code,
            phone=company.phone,
            email=company.email,
            tax_identifier=company.tax_identifier,
            registration_number=company.registration_number,
            logo_path=logo_path,
        )

    @staticmethod
    def _fmt(value: Decimal | None) -> str:
        if value is None:
            return ""
        v = value
        if v == _ZERO:
            return "–"
        if v < 0:
            return f"({abs(v):,.2f})"
        return f"{v:,.2f}"
