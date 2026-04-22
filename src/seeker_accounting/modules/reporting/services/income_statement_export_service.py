"""Export service for Income Statement reports (IAS and OHADA).

Each income-statement variant produces its own intentional, statement-specific
section layout for the renderers:

* **IAS** — one section, 3-column (Ref | Description | Amount), hierarchical
  with groups / lines / formulas.  Summary shows key profit/loss lines.
* **OHADA** — one section, 3-column (Ref | Description | Amount), flat with
  dynamic section headers embedded as ``section`` rows.  Highlight lines
  (XA, XE, XG, etc.) get visual emphasis.  Summary uses highlight codes.
"""

from __future__ import annotations

from decimal import Decimal

from seeker_accounting.modules.companies.services.company_logo_service import CompanyLogoService
from seeker_accounting.modules.companies.services.company_service import CompanyService
from seeker_accounting.modules.reporting.dto.ias_income_statement_dto import (
    IasIncomeStatementLineDTO,
    IasIncomeStatementReportDTO,
)
from seeker_accounting.modules.reporting.dto.ohada_income_statement_dto import (
    OhadaIncomeStatementLineDTO,
    OhadaIncomeStatementReportDTO,
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


class IncomeStatementExportService:
    """Exports IAS and OHADA income statements to PDF / Word / Excel."""

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
    # IAS Income Statement
    # ==================================================================

    def export_ias(
        self,
        report: IasIncomeStatementReportDTO,
        company_id: int,
        result: StatementExportResult,
    ) -> None:
        company_info = self._build_company_info(company_id)
        section = self._ias_section(report)
        summary = self._ias_summary(report)
        date_label = self._period_label(report.date_from, report.date_to)

        kwargs = dict(
            title="Statement of Profit or Loss",
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

    def _ias_section(self, report: IasIncomeStatementReportDTO) -> StatementTableSection:
        """Single table section for the IAS income statement."""
        rows: list[StatementExportRow] = []
        for line in report.lines:
            rows.append(
                StatementExportRow(
                    row_kind=line.row_kind_code,
                    indent_level=line.indent_level,
                    ref_code=line.code,
                    label=line.label,
                    amounts=(line.signed_amount,),
                )
            )
        return StatementTableSection(
            heading=None,
            column_headers=("Ref", "Description", "Amount"),
            rows=tuple(rows),
            column_widths=(10.0, 55.0, 20.0),
        )

    def _ias_summary(self, report: IasIncomeStatementReportDTO) -> list[tuple[str, str]]:
        summary: list[tuple[str, str]] = []
        summary_labels = {
            "GROSS_PROFIT": "Gross Profit",
            "OPERATING_PROFIT": "Operating Profit",
            "PROFIT_BEFORE_TAX": "Profit Before Tax",
            "PROFIT_FOR_PERIOD": "Profit for the Period",
        }
        line_map = {line.code: line for line in report.lines}
        for code in report.summary_line_codes:
            label = summary_labels.get(code, code)
            line = line_map.get(code)
            value = self._fmt(line.signed_amount if line else None)
            summary.append((label, value))
        return summary

    # ==================================================================
    # OHADA Income Statement
    # ==================================================================

    def export_ohada(
        self,
        report: OhadaIncomeStatementReportDTO,
        company_id: int,
        result: StatementExportResult,
    ) -> None:
        company_info = self._build_company_info(company_id)
        section = self._ohada_section(report)
        summary = self._ohada_summary(report)
        date_label = self._period_label(report.date_from, report.date_to)

        kwargs = dict(
            title="Compte de Résultat — OHADA SYSCOHADA",
            subtitle=None,
            date_label=date_label,
            company=company_info,
            sections=[section],
            summary_pairs=summary,
            output_path=result.output_path,
            page_size=result.page_size,
            orientation=result.orientation,
        )

        self._dispatch(result.format, kwargs)

    def _ohada_section(self, report: OhadaIncomeStatementReportDTO) -> StatementTableSection:
        """Single table section with dynamic section headers for the OHADA IS."""
        rows: list[StatementExportRow] = []
        current_section: str | None = None

        for line in report.lines:
            # Inject section header on section change
            if line.section_title and line.section_title != current_section:
                current_section = line.section_title
                rows.append(
                    StatementExportRow(
                        row_kind="section",
                        indent_level=0,
                        ref_code="",
                        label=current_section,
                        amounts=(None,),
                    )
                )

            is_highlight = line.code in report.highlight_line_codes
            rows.append(
                StatementExportRow(
                    row_kind="formula" if line.is_formula else "line",
                    indent_level=0,
                    ref_code=line.code,
                    label=line.label,
                    amounts=(line.signed_amount,),
                    is_highlight=is_highlight,
                )
            )

        return StatementTableSection(
            heading=None,
            column_headers=("Ref", "Description", "Montant (Amount)"),
            rows=tuple(rows),
            column_widths=(10.0, 55.0, 20.0),
        )

    def _ohada_summary(self, report: OhadaIncomeStatementReportDTO) -> list[tuple[str, str]]:
        summary: list[tuple[str, str]] = []
        line_map = {line.code: line for line in report.lines}
        for code in report.highlight_line_codes:
            line = line_map.get(code)
            if line:
                summary.append((f"{code} — {line.label}", self._fmt(line.signed_amount)))
        return summary

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
    def _period_label(date_from, date_to) -> str:
        if date_from and date_to:
            return (
                f"For the period {date_from.strftime('%d %B %Y')} "
                f"to {date_to.strftime('%d %B %Y')}"
            )
        return "Period not specified"

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
