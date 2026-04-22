from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.reporting.dto.ohada_balance_sheet_dto import (
    OhadaBalanceSheetAccountContributionDTO,
    OhadaBalanceSheetLineDTO,
    OhadaBalanceSheetLineDetailDTO,
    OhadaBalanceSheetReportDTO,
    OhadaBalanceSheetWarningDTO,
)
from seeker_accounting.modules.reporting.dto.print_preview_dto import (
    PrintPreviewMetaDTO,
    PrintPreviewRowDTO,
)
from seeker_accounting.modules.reporting.dto.reporting_filter_dto import ReportingFilterDTO
from seeker_accounting.modules.reporting.repositories.ohada_balance_sheet_repository import (
    OhadaBalanceSheetAccountRow,
    OhadaBalanceSheetRepository,
)
from seeker_accounting.modules.reporting.services.balance_sheet_template_service import (
    BalanceSheetTemplateService,
)
from seeker_accounting.modules.reporting.services.ohada_period_result_service import (
    OhadaPeriodResultService,
)
from seeker_accounting.modules.reporting.specs.ohada_balance_sheet_spec import (
    OHADA_BALANCE_MODE_CREDIT,
    OHADA_BALANCE_MODE_DEBIT,
    OHADA_BALANCE_MODE_LIABILITY_SIGNED,
    OHADA_BALANCE_SHEET_ALL_PREFIXES,
    OHADA_BALANCE_SHEET_ASSET_LINES,
    OHADA_BALANCE_SHEET_BASE_LINE_SPECS,
    OHADA_BALANCE_SHEET_LIABILITY_LINES,
    OHADA_BALANCE_SHEET_SPEC_BY_CODE,
    OHADA_BALANCE_SHEET_TOTAL_LINE_SPECS,
    OHADA_BALANCE_SHEET_VERSION,
    OhadaBalanceSheetLineSpec,
    OhadaBalanceSheetSelectorSpec,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

OhadaBalanceSheetRepositoryFactory = Callable[[Session], OhadaBalanceSheetRepository]

_ZERO = Decimal("0.00")
_UNCLASSIFIED_LINE_CODE = "UNCLASSIFIED"


@dataclass(frozen=True, slots=True)
class _ComputedLine:
    spec: OhadaBalanceSheetLineSpec
    gross_amount: Decimal | None
    contra_amount: Decimal | None
    net_amount: Decimal | None
    accounts: tuple[OhadaBalanceSheetAccountContributionDTO, ...]


class OhadaBalanceSheetService:
    """Builds the locked OHADA balance sheet from posted accounting truth."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        ohada_balance_sheet_repository_factory: OhadaBalanceSheetRepositoryFactory,
        balance_sheet_template_service: BalanceSheetTemplateService,
        ohada_period_result_service: OhadaPeriodResultService,
        permission_service: PermissionService,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._ohada_balance_sheet_repository_factory = ohada_balance_sheet_repository_factory
        self._balance_sheet_template_service = balance_sheet_template_service
        self._ohada_period_result_service = ohada_period_result_service
        self._permission_service = permission_service

    def get_statement(
        self,
        filter_dto: ReportingFilterDTO,
        template_code: str | None = None,
    ) -> OhadaBalanceSheetReportDTO:
        self._permission_service.require_permission("reports.ohada_balance_sheet.view")
        company_id, statement_date = self._normalize_filter(filter_dto)
        template = self._balance_sheet_template_service.get_template(template_code)
        rows = self._load_rows(company_id, statement_date)
        derived_ytd_result = self._load_ytd_profit_loss(company_id, statement_date)
        computed = self._compute_lines(rows, derived_ytd_result=derived_ytd_result)
        warnings, unclassified_accounts, has_chart_coverage = self._build_warnings(rows, computed)

        asset_lines = tuple(self._to_line_dto(computed[spec.code]) for spec in OHADA_BALANCE_SHEET_ASSET_LINES)
        liability_lines = tuple(
            self._to_line_dto(computed[spec.code]) for spec in OHADA_BALANCE_SHEET_LIABILITY_LINES
        )
        total_assets = computed["BZ"].net_amount or _ZERO
        total_liabilities = computed["DZ"].net_amount or _ZERO
        has_posted_activity = any(row.total_debit != _ZERO or row.total_credit != _ZERO for row in rows)
        has_classified_activity = any(
            (computed[spec.code].net_amount or _ZERO) != _ZERO for spec in OHADA_BALANCE_SHEET_BASE_LINE_SPECS
        )

        return OhadaBalanceSheetReportDTO(
            company_id=company_id,
            statement_date=statement_date,
            spec_version=OHADA_BALANCE_SHEET_VERSION,
            template_code=template.template_code,
            template_title=template.template_title,
            asset_lines=asset_lines,
            liability_lines=liability_lines,
            warnings=warnings,
            unclassified_accounts=unclassified_accounts,
            has_chart_coverage=has_chart_coverage,
            has_posted_activity=has_posted_activity,
            has_classified_activity=has_classified_activity,
            total_assets=total_assets,
            total_liabilities_and_equity=total_liabilities,
            balance_difference=(total_assets - total_liabilities).quantize(Decimal("0.01")),
        )

    def get_line_detail(
        self,
        filter_dto: ReportingFilterDTO,
        line_code: str,
        template_code: str | None = None,
    ) -> OhadaBalanceSheetLineDetailDTO:
        normalized_code = (line_code or "").strip().upper()
        report = self.get_statement(filter_dto, template_code=template_code)
        company_id, statement_date = self._normalize_filter(filter_dto)

        if normalized_code == _UNCLASSIFIED_LINE_CODE:
            return OhadaBalanceSheetLineDetailDTO(
                company_id=company_id,
                statement_date=statement_date,
                line_code=_UNCLASSIFIED_LINE_CODE,
                line_label="Unclassified OHADA Balance Sheet Accounts",
                side_code="support",
                row_kind_code="support",
                gross_amount=None,
                contra_amount=None,
                net_amount=sum((item.amount for item in report.unclassified_accounts), _ZERO),
                accounts=report.unclassified_accounts,
                warnings=tuple(
                    warning
                    for warning in report.warnings
                    if warning.code == "unclassified_balance_sheet_accounts"
                ),
            )

        line_lookup = {line.code: line for line in (*report.asset_lines, *report.liability_lines)}
        line = line_lookup.get(normalized_code)
        if line is None:
            raise NotFoundError(f"OHADA balance sheet line {normalized_code} was not found.")

        rows = self._load_rows(company_id, statement_date)
        derived_ytd_result = self._load_ytd_profit_loss(company_id, statement_date)
        computed = self._compute_lines(rows, derived_ytd_result=derived_ytd_result)
        detail = computed[normalized_code]
        return OhadaBalanceSheetLineDetailDTO(
            company_id=company_id,
            statement_date=statement_date,
            line_code=line.code,
            line_label=line.label,
            side_code=line.side_code,
            row_kind_code=line.row_kind_code,
            gross_amount=line.gross_amount,
            contra_amount=line.contra_amount,
            net_amount=line.net_amount,
            accounts=detail.accounts,
            warnings=tuple(
                warning
                for warning in report.warnings
                if normalized_code in warning.affected_line_codes
            ),
        )

    def list_unclassified_accounts(
        self,
        filter_dto: ReportingFilterDTO,
        template_code: str | None = None,
    ) -> OhadaBalanceSheetLineDetailDTO:
        return self.get_line_detail(filter_dto, _UNCLASSIFIED_LINE_CODE, template_code=template_code)

    def build_print_preview_meta(
        self,
        report_dto: OhadaBalanceSheetReportDTO,
        company_name: str,
    ) -> PrintPreviewMetaDTO:
        filter_summary = (
            f"Template: {report_dto.template_title} | "
            f"Unclassified: {len(report_dto.unclassified_accounts)} | "
            f"Difference: {self._fmt(report_dto.balance_difference)}"
        )
        return PrintPreviewMetaDTO(
            report_title="OHADA Balance Sheet",
            company_name=company_name,
            period_label=self._format_statement_date(report_dto.statement_date),
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            filter_summary=filter_summary,
            template_title=report_dto.template_title,
            amount_headers=("Gross", "Deprec./Prov.", "Net / Amount"),
            rows=tuple(self._build_preview_rows(report_dto)),
        )

    def _load_rows(self, company_id: int, statement_date: date | None) -> list[OhadaBalanceSheetAccountRow]:
        with self._unit_of_work_factory() as uow:
            repo = self._ohada_balance_sheet_repository_factory(uow.session)
            return repo.list_balance_snapshot(company_id, statement_date)

    def _load_ytd_profit_loss(self, company_id: int, statement_date: date | None) -> Decimal:
        return self._ohada_period_result_service.compute_period_result(
            company_id=company_id,
            date_from=None,
            date_to=statement_date,
        )

    def _compute_lines(
        self,
        rows: list[OhadaBalanceSheetAccountRow],
        derived_ytd_result: Decimal = _ZERO,
    ) -> dict[str, _ComputedLine]:
        computed: dict[str, _ComputedLine] = {}
        for spec in OHADA_BALANCE_SHEET_BASE_LINE_SPECS:
            gross_amount = _ZERO if spec.side_code == "assets" else None
            contra_amount = _ZERO if spec.side_code == "assets" else None
            net_amount = _ZERO
            account_map: dict[tuple[int, str], OhadaBalanceSheetAccountContributionDTO] = {}

            for row in rows:
                for selector in spec.selectors:
                    if not self._matches_selector(row.account_code, selector):
                        continue
                    amount = self._compute_selector_amount(row, selector.balance_mode)
                    if amount == _ZERO:
                        continue
                    account_map[(row.account_id, selector.contribution_kind_code)] = (
                        OhadaBalanceSheetAccountContributionDTO(
                            account_id=row.account_id,
                            account_code=row.account_code,
                            account_name=row.account_name,
                            account_class_code=row.account_class_code,
                            line_code=spec.code,
                            line_label=spec.label,
                            contribution_kind_code=selector.contribution_kind_code,
                            total_debit=row.total_debit,
                            total_credit=row.total_credit,
                            amount=amount,
                        )
                    )
                    if spec.side_code == "assets":
                        if selector.contribution_kind_code == "gross":
                            gross_amount = (gross_amount or _ZERO) + amount
                        else:
                            contra_amount = (contra_amount or _ZERO) + amount
                    else:
                        net_amount += amount

            if spec.side_code == "assets":
                net_amount = (gross_amount or _ZERO) - (contra_amount or _ZERO)

            computed[spec.code] = _ComputedLine(
                spec=spec,
                gross_amount=None if spec.side_code != "assets" else (gross_amount or _ZERO),
                contra_amount=None if spec.side_code != "assets" else (contra_amount or _ZERO),
                net_amount=net_amount,
                accounts=tuple(
                    sorted(
                        account_map.values(),
                        key=lambda item: (item.account_code, item.contribution_kind_code, item.account_id),
                    )
                ),
            )

        # Inject derived YTD P&L into CI (current-year result) before totals.
        # After closing entries, P&L accounts are zeroed so derived_ytd_result == 0;
        # before closing, the closing-result account (prefix 13) is zero.
        # The sum is always correct and never double-counts.
        if derived_ytd_result != _ZERO and "CI" in computed:
            ci = computed["CI"]
            computed["CI"] = _ComputedLine(
                spec=ci.spec,
                gross_amount=ci.gross_amount,
                contra_amount=ci.contra_amount,
                net_amount=(ci.net_amount or _ZERO) + derived_ytd_result,
                accounts=ci.accounts,
            )

        for spec in OHADA_BALANCE_SHEET_TOTAL_LINE_SPECS:
            gross_amount = _ZERO if spec.side_code == "assets" else None
            contra_amount = _ZERO if spec.side_code == "assets" else None
            net_amount = _ZERO
            merged_accounts: dict[tuple[int, str], OhadaBalanceSheetAccountContributionDTO] = {}
            for component_code in spec.total_components:
                component = computed[component_code]
                if spec.side_code == "assets":
                    gross_amount = (gross_amount or _ZERO) + (component.gross_amount or _ZERO)
                    contra_amount = (contra_amount or _ZERO) + (component.contra_amount or _ZERO)
                net_amount += component.net_amount or _ZERO
                for account in component.accounts:
                    key = (account.account_id, account.contribution_kind_code)
                    existing = merged_accounts.get(key)
                    if existing is None:
                        merged_accounts[key] = account
                        continue
                    merged_accounts[key] = OhadaBalanceSheetAccountContributionDTO(
                        account_id=existing.account_id,
                        account_code=existing.account_code,
                        account_name=existing.account_name,
                        account_class_code=existing.account_class_code,
                        line_code=spec.code,
                        line_label=spec.label,
                        contribution_kind_code=existing.contribution_kind_code,
                        total_debit=existing.total_debit + account.total_debit,
                        total_credit=existing.total_credit + account.total_credit,
                        amount=existing.amount + account.amount,
                    )

            computed[spec.code] = _ComputedLine(
                spec=spec,
                gross_amount=None if spec.side_code != "assets" else (gross_amount or _ZERO),
                contra_amount=None if spec.side_code != "assets" else (contra_amount or _ZERO),
                net_amount=net_amount,
                accounts=tuple(
                    sorted(
                        merged_accounts.values(),
                        key=lambda item: (item.account_code, item.contribution_kind_code, item.account_id),
                    )
                ),
            )

        for spec in OHADA_BALANCE_SHEET_SPEC_BY_CODE.values():
            if spec.code not in computed:
                computed[spec.code] = _ComputedLine(spec=spec, gross_amount=None, contra_amount=None, net_amount=None, accounts=())
        return computed

    def _build_warnings(
        self,
        rows: list[OhadaBalanceSheetAccountRow],
        computed: dict[str, _ComputedLine],
    ) -> tuple[
        tuple[OhadaBalanceSheetWarningDTO, ...],
        tuple[OhadaBalanceSheetAccountContributionDTO, ...],
        bool,
    ]:
        warnings: list[OhadaBalanceSheetWarningDTO] = []
        matched_account_ids = {
            account.account_id
            for spec in OHADA_BALANCE_SHEET_BASE_LINE_SPECS
            for account in computed[spec.code].accounts
        }
        has_chart_coverage = any(
            any(row.account_code.startswith(prefix) for prefix in OHADA_BALANCE_SHEET_ALL_PREFIXES)
            for row in rows
        )
        missing_line_codes = tuple(
            spec.code
            for spec in OHADA_BALANCE_SHEET_BASE_LINE_SPECS
            if not any(
                self._matches_selector(row.account_code, selector)
                for row in rows
                for selector in spec.selectors
            )
        )
        if missing_line_codes:
            warnings.append(
                OhadaBalanceSheetWarningDTO(
                    code="missing_ohada_balance_sheet_prefixes",
                    title="Incomplete OHADA balance sheet coverage",
                    message=(
                        "Some locked OHADA balance sheet lines have no matching accounts in the "
                        "company chart. Those lines remain zero until the chart is completed."
                    ),
                    affected_line_codes=missing_line_codes,
                )
            )

        unclassified_accounts = tuple(
            sorted(
                (
                    OhadaBalanceSheetAccountContributionDTO(
                        account_id=row.account_id,
                        account_code=row.account_code,
                        account_name=row.account_name,
                        account_class_code=row.account_class_code,
                        line_code=None,
                        line_label=None,
                        contribution_kind_code="unclassified",
                        total_debit=row.total_debit,
                        total_credit=row.total_credit,
                        amount=self._balance_magnitude(row),
                    )
                    for row in rows
                    if self._is_balance_sheet_account(row)
                    and row.account_id not in matched_account_ids
                    and self._balance_magnitude(row) != _ZERO
                ),
                key=lambda item: (item.account_code, item.account_id),
            )
        )
        if unclassified_accounts:
            warnings.append(
                OhadaBalanceSheetWarningDTO(
                    code="unclassified_balance_sheet_accounts",
                    title="Unclassified OHADA balance sheet accounts",
                    message=(
                        "Some posted balance sheet accounts fall outside the locked OHADA mapping. "
                        "They are excluded from statement lines and should be reviewed."
                    ),
                )
            )

        if not has_chart_coverage:
            warnings.append(
                OhadaBalanceSheetWarningDTO(
                    code="no_ohada_balance_sheet_coverage",
                    title="No OHADA balance sheet coverage detected",
                    message=(
                        "No company accounts were found under the locked OHADA balance sheet prefixes. "
                        "Seed or review the company chart before relying on this statement."
                    ),
                )
            )
        return tuple(warnings), unclassified_accounts, has_chart_coverage

    def _to_line_dto(self, line: _ComputedLine) -> OhadaBalanceSheetLineDTO:
        return OhadaBalanceSheetLineDTO(
            code=line.spec.code,
            reference_code=line.spec.reference_code,
            label=line.spec.label,
            side_code=line.spec.side_code,
            section_code=line.spec.section_code,
            section_title=line.spec.section_title,
            row_kind_code=line.spec.row_kind_code,
            display_order=line.spec.display_order,
            gross_amount=line.gross_amount,
            contra_amount=line.contra_amount,
            net_amount=line.net_amount,
            can_drilldown=bool(line.accounts),
            component_codes=line.spec.total_components,
        )

    @staticmethod
    def _matches_selector(account_code: str, selector: OhadaBalanceSheetSelectorSpec) -> bool:
        normalized = (account_code or "").strip()
        if not normalized:
            return False
        is_exact_match = normalized in selector.include_exact_codes
        is_prefix_match = any(normalized.startswith(prefix) for prefix in selector.include_prefixes)
        if not (is_exact_match or is_prefix_match):
            return False
        if normalized in selector.exclude_exact_codes:
            return False
        return not any(normalized.startswith(prefix) for prefix in selector.exclude_prefixes)

    @staticmethod
    def _compute_selector_amount(row: OhadaBalanceSheetAccountRow, balance_mode: str) -> Decimal:
        debit_balance = (row.total_debit - row.total_credit).quantize(Decimal("0.01"))
        credit_balance = (row.total_credit - row.total_debit).quantize(Decimal("0.01"))
        if balance_mode == OHADA_BALANCE_MODE_DEBIT:
            return max(debit_balance, _ZERO)
        if balance_mode == OHADA_BALANCE_MODE_CREDIT:
            return max(credit_balance, _ZERO)
        if balance_mode == OHADA_BALANCE_MODE_LIABILITY_SIGNED:
            return credit_balance
        return _ZERO

    @staticmethod
    def _balance_magnitude(row: OhadaBalanceSheetAccountRow) -> Decimal:
        debit_balance = (row.total_debit - row.total_credit).quantize(Decimal("0.01"))
        credit_balance = (row.total_credit - row.total_debit).quantize(Decimal("0.01"))
        return max(max(debit_balance, _ZERO), max(credit_balance, _ZERO))

    @staticmethod
    def _is_balance_sheet_account(row: OhadaBalanceSheetAccountRow) -> bool:
        if row.account_class_code in {"1", "2", "3", "4", "5"}:
            return True
        return (row.account_code or "").startswith(("1", "2", "3", "4", "5"))

    @staticmethod
    def _format_statement_date(statement_date: date | None) -> str:
        if statement_date is None:
            return "As at latest posted activity"
        return f"As at {statement_date.strftime('%d %b %Y')}"

    def _build_preview_rows(self, report_dto: OhadaBalanceSheetReportDTO) -> list[PrintPreviewRowDTO]:
        rows: list[PrintPreviewRowDTO] = []
        for line in report_dto.asset_lines:
            rows.append(
                PrintPreviewRowDTO(
                    row_type="section" if line.row_kind_code == "section" else ("subtotal" if line.row_kind_code == "total" else "line"),
                    reference_code=line.reference_code,
                    label=line.label,
                    amount_text=self._fmt(line.gross_amount) if line.gross_amount is not None else "",
                    secondary_amount_text=self._fmt(line.contra_amount) if line.contra_amount is not None else "",
                    tertiary_amount_text=self._fmt(line.net_amount) if line.net_amount is not None else "",
                )
            )
        rows.append(PrintPreviewRowDTO(row_type="section", reference_code=None, label="LIABILITIES", amount_text="", secondary_amount_text="", tertiary_amount_text=""))
        for line in report_dto.liability_lines:
            rows.append(
                PrintPreviewRowDTO(
                    row_type="section" if line.row_kind_code == "section" else ("subtotal" if line.row_kind_code == "total" else "line"),
                    reference_code=line.reference_code,
                    label=line.label,
                    amount_text="",
                    secondary_amount_text="",
                    tertiary_amount_text=self._fmt(line.net_amount) if line.net_amount is not None else "",
                )
            )
        return rows

    def _normalize_filter(self, filter_dto: ReportingFilterDTO) -> tuple[int, date | None]:
        company_id = filter_dto.company_id
        if not isinstance(company_id, int) or company_id <= 0:
            raise ValidationError("Select an active company to run the OHADA balance sheet.")
        if not filter_dto.posted_only:
            raise ValidationError("OHADA balance sheet reporting is limited to posted journals.")
        date_from = filter_dto.date_from
        date_to = filter_dto.date_to
        if date_from and date_to and date_to < date_from:
            raise ValidationError("The 'To' date must be on or after the 'From' date.")
        return company_id, date_to or date_from

    @staticmethod
    def _fmt(amount: Decimal | None) -> str:
        value = amount or _ZERO
        if value == _ZERO:
            return "0.00"
        return f"{value:,.2f}"
