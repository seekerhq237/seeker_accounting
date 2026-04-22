from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.reporting.dto.ias_balance_sheet_dto import (
    IasBalanceSheetAccountContributionDTO,
    IasBalanceSheetLineDTO,
    IasBalanceSheetLineDetailDTO,
    IasBalanceSheetReportDTO,
    IasBalanceSheetWarningDTO,
)
from seeker_accounting.modules.reporting.dto.print_preview_dto import (
    PrintPreviewMetaDTO,
    PrintPreviewRowDTO,
)
from seeker_accounting.modules.reporting.dto.reporting_filter_dto import ReportingFilterDTO
from seeker_accounting.modules.reporting.repositories.ias_balance_sheet_repository import (
    IasBalanceSheetAccountRow,
    IasBalanceSheetRepository,
)
from seeker_accounting.modules.reporting.services.balance_sheet_template_service import (
    BalanceSheetTemplateService,
)
from seeker_accounting.modules.reporting.specs.ias_balance_sheet_spec import (
    IAS_BALANCE_MODE_ASSET_SIGNED,
    IAS_BALANCE_MODE_CREDIT,
    IAS_BALANCE_MODE_DEBIT,
    IAS_BALANCE_MODE_LIABILITY_SIGNED,
    IAS_BALANCE_SHEET_LINE_SPECS,
    IAS_BALANCE_SHEET_RELEVANT_CLASS_CODES,
    IAS_BALANCE_SHEET_RELEVANT_SECTION_CODES,
    IAS_BALANCE_SHEET_SPEC_BY_CODE,
    IAS_BALANCE_SHEET_VERSION,
    IasBalanceSheetLineSpec,
    IasBalanceSheetSelectorSpec,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

IasBalanceSheetRepositoryFactory = Callable[[Session], IasBalanceSheetRepository]

_ZERO = Decimal("0.00")
_UNCLASSIFIED_LINE_CODE = "UNCLASSIFIED"


@dataclass(frozen=True, slots=True)
class _ComputedLine:
    amount: Decimal
    accounts: tuple[IasBalanceSheetAccountContributionDTO, ...]


class IasBalanceSheetService:
    """Builds the locked IAS/IFRS statement of financial position."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        ias_balance_sheet_repository_factory: IasBalanceSheetRepositoryFactory,
        balance_sheet_template_service: BalanceSheetTemplateService,
        permission_service: PermissionService,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._ias_balance_sheet_repository_factory = ias_balance_sheet_repository_factory
        self._balance_sheet_template_service = balance_sheet_template_service
        self._permission_service = permission_service

    def get_statement(
        self,
        filter_dto: ReportingFilterDTO,
        template_code: str | None = None,
    ) -> IasBalanceSheetReportDTO:
        self._permission_service.require_permission("reports.ias_balance_sheet.view")
        company_id, statement_date = self._normalize_filter(filter_dto)
        template = self._balance_sheet_template_service.get_template(template_code)
        rows = self._load_rows(company_id, statement_date)
        derived_ytd_result = self._load_ytd_profit_loss(company_id, statement_date)
        computed = self._compute_lines(rows, derived_ytd_result=derived_ytd_result)
        warnings, unclassified_accounts = self._build_warnings(rows, computed)
        lines = tuple(self._to_line_dto(spec, computed[spec.code]) for spec in IAS_BALANCE_SHEET_LINE_SPECS)
        total_assets = computed["TOTAL_ASSETS"].amount
        total_equity_liabilities = computed["TOTAL_EQUITY_AND_LIABILITIES"].amount
        has_posted_activity = any(row.total_debit != _ZERO or row.total_credit != _ZERO for row in rows)
        has_classified_activity = any(
            computed[spec.code].amount != _ZERO
            for spec in IAS_BALANCE_SHEET_LINE_SPECS
            if spec.is_classification_target
        )

        if not has_posted_activity:
            warnings = warnings + (
                IasBalanceSheetWarningDTO(
                    code="no_posted_balance_sheet_activity",
                    severity_code="info",
                    title="No posted balances in scope",
                    message=(
                        "The selected statement date has no posted balance sheet activity for the "
                        "locked IAS/IFRS presentation."
                    ),
                ),
            )

        return IasBalanceSheetReportDTO(
            company_id=company_id,
            statement_date=statement_date,
            spec_version=IAS_BALANCE_SHEET_VERSION,
            template_code=template.template_code,
            template_title=template.template_title,
            lines=lines,
            warnings=warnings,
            unclassified_accounts=unclassified_accounts,
            has_posted_activity=has_posted_activity,
            has_classified_activity=has_classified_activity,
            total_assets=total_assets,
            total_equity_and_liabilities=total_equity_liabilities,
            balance_difference=(total_assets - total_equity_liabilities).quantize(Decimal("0.01")),
        )

    def get_line_detail(
        self,
        filter_dto: ReportingFilterDTO,
        line_code: str,
        template_code: str | None = None,
    ) -> IasBalanceSheetLineDetailDTO:
        normalized_code = (line_code or "").strip().upper()
        report = self.get_statement(filter_dto, template_code=template_code)
        company_id, statement_date = self._normalize_filter(filter_dto)

        if normalized_code == _UNCLASSIFIED_LINE_CODE:
            return IasBalanceSheetLineDetailDTO(
                company_id=company_id,
                statement_date=statement_date,
                line_code=_UNCLASSIFIED_LINE_CODE,
                line_label="Unclassified Balance Sheet Accounts",
                row_kind_code="support",
                amount=sum((item.amount for item in report.unclassified_accounts), _ZERO),
                accounts=report.unclassified_accounts,
                warnings=tuple(
                    warning
                    for warning in report.warnings
                    if warning.code == "unclassified_ias_balance_sheet_accounts"
                ),
            )

        line = next((item for item in report.lines if item.code == normalized_code), None)
        if line is None:
            raise NotFoundError(f"IAS balance sheet line {normalized_code} was not found.")
        if not line.can_drilldown:
            raise ValidationError(f"IAS balance sheet line {normalized_code} has no contributing accounts.")

        rows = self._load_rows(company_id, statement_date)
        derived_ytd_result = self._load_ytd_profit_loss(company_id, statement_date)
        computed = self._compute_lines(rows, derived_ytd_result=derived_ytd_result)
        return IasBalanceSheetLineDetailDTO(
            company_id=company_id,
            statement_date=statement_date,
            line_code=line.code,
            line_label=line.label,
            row_kind_code=line.row_kind_code,
            amount=line.amount or _ZERO,
            accounts=computed[normalized_code].accounts,
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
    ) -> IasBalanceSheetLineDetailDTO:
        return self.get_line_detail(filter_dto, _UNCLASSIFIED_LINE_CODE, template_code=template_code)

    def build_print_preview_meta(
        self,
        report_dto: IasBalanceSheetReportDTO,
        company_name: str,
    ) -> PrintPreviewMetaDTO:
        filter_summary = (
            f"Template: {report_dto.template_title} | "
            f"Unclassified: {len(report_dto.unclassified_accounts)} | "
            f"Difference: {self._fmt(report_dto.balance_difference)}"
        )
        return PrintPreviewMetaDTO(
            report_title="IAS/IFRS Balance Sheet",
            company_name=company_name,
            period_label=self._format_statement_date(report_dto.statement_date),
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            filter_summary=filter_summary,
            template_title=report_dto.template_title,
            rows=tuple(self._build_preview_rows(report_dto)),
        )

    def _load_rows(self, company_id: int, statement_date: date | None) -> list[IasBalanceSheetAccountRow]:
        with self._unit_of_work_factory() as uow:
            repo = self._ias_balance_sheet_repository_factory(uow.session)
            return repo.list_balance_snapshot(company_id, statement_date)

    def _load_ytd_profit_loss(self, company_id: int, statement_date: date | None) -> Decimal:
        with self._unit_of_work_factory() as uow:
            repo = self._ias_balance_sheet_repository_factory(uow.session)
            return repo.sum_ytd_profit_loss(company_id, statement_date)

    def _compute_lines(
        self,
        rows: list[IasBalanceSheetAccountRow],
        derived_ytd_result: Decimal = _ZERO,
    ) -> dict[str, _ComputedLine]:
        cache: dict[str, _ComputedLine] = {}

        def resolve(spec: IasBalanceSheetLineSpec) -> _ComputedLine:
            if spec.code in cache:
                return cache[spec.code]

            if spec.is_classification_target:
                contributions: dict[int, IasBalanceSheetAccountContributionDTO] = {}
                for row in rows:
                    for selector in spec.selectors:
                        if not self._matches_selector(row.account_code, selector):
                            continue
                        amount = self._compute_amount(row, selector.amount_mode)
                        if amount == _ZERO:
                            continue
                        existing = contributions.get(row.account_id)
                        if existing is None:
                            contributions[row.account_id] = IasBalanceSheetAccountContributionDTO(
                                account_id=row.account_id,
                                account_code=row.account_code,
                                account_name=row.account_name,
                                account_class_code=row.account_class_code,
                                account_type_code=row.account_type_code,
                                account_type_section_code=row.account_type_section_code,
                                normal_balance=row.normal_balance,
                                line_code=spec.code,
                                line_label=spec.label,
                                contribution_kind_code=selector.contribution_kind_code,
                                total_debit=row.total_debit,
                                total_credit=row.total_credit,
                                amount=amount,
                                account_is_active=row.is_active,
                                allow_manual_posting=row.allow_manual_posting,
                                is_control_account=row.is_control_account,
                            )
                        else:
                            contributions[row.account_id] = IasBalanceSheetAccountContributionDTO(
                                account_id=existing.account_id,
                                account_code=existing.account_code,
                                account_name=existing.account_name,
                                account_class_code=existing.account_class_code,
                                account_type_code=existing.account_type_code,
                                account_type_section_code=existing.account_type_section_code,
                                normal_balance=existing.normal_balance,
                                line_code=existing.line_code,
                                line_label=existing.line_label,
                                contribution_kind_code=existing.contribution_kind_code,
                                total_debit=existing.total_debit + row.total_debit,
                                total_credit=existing.total_credit + row.total_credit,
                                amount=existing.amount + amount,
                                account_is_active=existing.account_is_active,
                                allow_manual_posting=existing.allow_manual_posting,
                                is_control_account=existing.is_control_account,
                            )
                amount = sum((item.amount for item in contributions.values()), _ZERO)
                if spec.code == "CURRENT_YEAR_RESULT":
                    amount += derived_ytd_result
                cache[spec.code] = _ComputedLine(
                    amount=amount,
                    accounts=self._sort_accounts(contributions),
                )
                return cache[spec.code]

            if spec.formula_components:
                merged: dict[int, IasBalanceSheetAccountContributionDTO] = {}
                amount = _ZERO
                for component_code in spec.formula_components:
                    component = resolve(IAS_BALANCE_SHEET_SPEC_BY_CODE[component_code])
                    amount += component.amount
                    self._merge_accounts(merged, component.accounts, spec.code, spec.label)
                cache[spec.code] = _ComputedLine(amount=amount, accounts=self._sort_accounts(merged))
                return cache[spec.code]

            if spec.aggregation_components:
                merged = {}
                amount = _ZERO
                for component_code in spec.aggregation_components:
                    component = resolve(IAS_BALANCE_SHEET_SPEC_BY_CODE[component_code])
                    amount += component.amount
                    self._merge_accounts(merged, component.accounts, spec.code, spec.label)
                cache[spec.code] = _ComputedLine(amount=amount, accounts=self._sort_accounts(merged))
                return cache[spec.code]

            cache[spec.code] = _ComputedLine(amount=_ZERO, accounts=())
            return cache[spec.code]

        for spec in IAS_BALANCE_SHEET_LINE_SPECS:
            resolve(spec)
        return cache

    def _build_warnings(
        self,
        rows: list[IasBalanceSheetAccountRow],
        computed: dict[str, _ComputedLine],
    ) -> tuple[tuple[IasBalanceSheetWarningDTO, ...], tuple[IasBalanceSheetAccountContributionDTO, ...]]:
        warnings: list[IasBalanceSheetWarningDTO] = []
        matched_account_ids = {
            account.account_id
            for spec in IAS_BALANCE_SHEET_LINE_SPECS
            if spec.is_classification_target
            for account in computed[spec.code].accounts
        }

        metadata_limited_codes = tuple(
            spec.code
            for spec in IAS_BALANCE_SHEET_LINE_SPECS
            if spec.is_classification_target and not spec.selectors
        )
        if metadata_limited_codes:
            warnings.append(
                IasBalanceSheetWarningDTO(
                    code="limited_ias_balance_sheet_metadata",
                    severity_code="warning",
                    title="Metadata-limited IAS classification",
                    message=(
                        "Some IAS balance sheet lines stay at zero because the current account metadata "
                        "does not safely distinguish them yet."
                    ),
                    affected_line_codes=metadata_limited_codes,
                )
            )

        invalid_accounts = tuple(
            row
            for row in rows
            if row.account_id in matched_account_ids
            and (not row.is_active or not row.allow_manual_posting)
            and self._has_balance(row)
        )
        for row in invalid_accounts:
            warnings.append(
                IasBalanceSheetWarningDTO(
                    code="inactive_or_non_postable_balance_sheet_account",
                    severity_code="warning",
                    title="Inactive or non-postable account in IAS balance sheet",
                    message=(
                        f"Account {row.account_code} | {row.account_name} contributed balance sheet activity "
                        "but is inactive or non-postable."
                    ),
                    account_id=row.account_id,
                )
            )

        unclassified_accounts = tuple(
            sorted(
                (
                    IasBalanceSheetAccountContributionDTO(
                        account_id=row.account_id,
                        account_code=row.account_code,
                        account_name=row.account_name,
                        account_class_code=row.account_class_code,
                        account_type_code=row.account_type_code,
                        account_type_section_code=row.account_type_section_code,
                        normal_balance=row.normal_balance,
                        line_code=_UNCLASSIFIED_LINE_CODE,
                        line_label="Unclassified Balance Sheet Account",
                        contribution_kind_code="unclassified",
                        total_debit=row.total_debit,
                        total_credit=row.total_credit,
                        amount=self._balance_magnitude(row),
                        account_is_active=row.is_active,
                        allow_manual_posting=row.allow_manual_posting,
                        is_control_account=row.is_control_account,
                    )
                    for row in rows
                    if self._is_relevant_account(row)
                    and row.account_id not in matched_account_ids
                    and self._balance_magnitude(row) != _ZERO
                ),
                key=lambda item: (item.account_code, item.account_id),
            )
        )
        if unclassified_accounts:
            warnings.append(
                IasBalanceSheetWarningDTO(
                    code="unclassified_ias_balance_sheet_accounts",
                    severity_code="warning",
                    title="Unclassified IAS balance sheet accounts",
                    message=(
                        "Some posted balance sheet accounts fall outside the locked IAS/IFRS "
                        "classification policy. Review them before relying on the statement."
                    ),
                )
            )
        return tuple(warnings), unclassified_accounts

    def _to_line_dto(self, spec: IasBalanceSheetLineSpec, computed: _ComputedLine) -> IasBalanceSheetLineDTO:
        indent_level = 0
        parent_code = spec.parent_code
        while parent_code:
            indent_level += 1
            parent_code = IAS_BALANCE_SHEET_SPEC_BY_CODE[parent_code].parent_code
        return IasBalanceSheetLineDTO(
            code=spec.code,
            label=spec.label,
            row_kind_code=spec.row_kind_code,
            parent_code=spec.parent_code,
            display_order=spec.display_order,
            indent_level=max(indent_level - 1, 0) if spec.parent_code else 0,
            amount=None if spec.row_kind_code == "section" else computed.amount,
            can_drilldown=bool(computed.accounts),
            is_formula=spec.is_formula,
            is_classification_target=spec.is_classification_target,
            aggregation_components=spec.aggregation_components,
            formula_components=spec.formula_components,
        )

    @staticmethod
    def _matches_selector(account_code: str, selector: IasBalanceSheetSelectorSpec) -> bool:
        normalized = (account_code or "").strip()
        if not normalized:
            return False
        if not any(normalized.startswith(prefix) for prefix in selector.include_prefixes):
            return False
        return not any(normalized.startswith(prefix) for prefix in selector.exclude_prefixes)

    @staticmethod
    def _compute_amount(row: IasBalanceSheetAccountRow, amount_mode: str) -> Decimal:
        debit_balance = (row.total_debit - row.total_credit).quantize(Decimal("0.01"))
        credit_balance = (row.total_credit - row.total_debit).quantize(Decimal("0.01"))
        if amount_mode == IAS_BALANCE_MODE_ASSET_SIGNED:
            return debit_balance
        if amount_mode == IAS_BALANCE_MODE_LIABILITY_SIGNED:
            return credit_balance
        if amount_mode == IAS_BALANCE_MODE_DEBIT:
            return max(debit_balance, _ZERO)
        if amount_mode == IAS_BALANCE_MODE_CREDIT:
            return max(credit_balance, _ZERO)
        return _ZERO

    def _merge_accounts(
        self,
        target: dict[int, IasBalanceSheetAccountContributionDTO],
        source: tuple[IasBalanceSheetAccountContributionDTO, ...],
        line_code: str,
        line_label: str,
    ) -> None:
        for account in source:
            existing = target.get(account.account_id)
            if existing is None:
                target[account.account_id] = IasBalanceSheetAccountContributionDTO(
                    account_id=account.account_id,
                    account_code=account.account_code,
                    account_name=account.account_name,
                    account_class_code=account.account_class_code,
                    account_type_code=account.account_type_code,
                    account_type_section_code=account.account_type_section_code,
                    normal_balance=account.normal_balance,
                    line_code=line_code,
                    line_label=line_label,
                    contribution_kind_code=account.contribution_kind_code,
                    total_debit=account.total_debit,
                    total_credit=account.total_credit,
                    amount=account.amount,
                    account_is_active=account.account_is_active,
                    allow_manual_posting=account.allow_manual_posting,
                    is_control_account=account.is_control_account,
                )
                continue
            target[account.account_id] = IasBalanceSheetAccountContributionDTO(
                account_id=existing.account_id,
                account_code=existing.account_code,
                account_name=existing.account_name,
                account_class_code=existing.account_class_code,
                account_type_code=existing.account_type_code,
                account_type_section_code=existing.account_type_section_code,
                normal_balance=existing.normal_balance,
                line_code=line_code,
                line_label=line_label,
                contribution_kind_code=existing.contribution_kind_code,
                total_debit=existing.total_debit + account.total_debit,
                total_credit=existing.total_credit + account.total_credit,
                amount=existing.amount + account.amount,
                account_is_active=existing.account_is_active,
                allow_manual_posting=existing.allow_manual_posting,
                is_control_account=existing.is_control_account,
            )

    @staticmethod
    def _sort_accounts(
        accounts: dict[int, IasBalanceSheetAccountContributionDTO],
    ) -> tuple[IasBalanceSheetAccountContributionDTO, ...]:
        return tuple(sorted(accounts.values(), key=lambda item: (item.account_code, item.account_id)))

    @staticmethod
    def _is_relevant_account(row: IasBalanceSheetAccountRow) -> bool:
        if row.account_class_code in IAS_BALANCE_SHEET_RELEVANT_CLASS_CODES:
            return True
        if (row.account_type_section_code or "").strip().upper() in IAS_BALANCE_SHEET_RELEVANT_SECTION_CODES:
            return True
        return (row.account_code or "").startswith(("1", "2", "3", "4", "5"))

    @staticmethod
    def _has_balance(row: IasBalanceSheetAccountRow) -> bool:
        return row.total_debit != _ZERO or row.total_credit != _ZERO

    @staticmethod
    def _balance_magnitude(row: IasBalanceSheetAccountRow) -> Decimal:
        debit_balance = (row.total_debit - row.total_credit).quantize(Decimal("0.01"))
        credit_balance = (row.total_credit - row.total_debit).quantize(Decimal("0.01"))
        return max(max(debit_balance, _ZERO), max(credit_balance, _ZERO))

    @staticmethod
    def _format_statement_date(statement_date: date | None) -> str:
        if statement_date is None:
            return "As at latest posted activity"
        return f"As at {statement_date.strftime('%d %b %Y')}"

    def _build_preview_rows(self, report_dto: IasBalanceSheetReportDTO) -> list[PrintPreviewRowDTO]:
        rows: list[PrintPreviewRowDTO] = []
        for line in report_dto.lines:
            indent = "    " * line.indent_level
            rows.append(
                PrintPreviewRowDTO(
                    row_type="section" if line.row_kind_code == "section" else ("subtotal" if line.is_formula or line.row_kind_code == "group" else "line"),
                    reference_code=line.code if line.row_kind_code != "section" else None,
                    label=f"{indent}{line.label}",
                    amount_text="" if line.amount is None else self._fmt(line.amount),
                )
            )
        return rows

    def _normalize_filter(self, filter_dto: ReportingFilterDTO) -> tuple[int, date | None]:
        company_id = filter_dto.company_id
        if not isinstance(company_id, int) or company_id <= 0:
            raise ValidationError("Select an active company to run the IAS/IFRS balance sheet.")
        if not filter_dto.posted_only:
            raise ValidationError("IAS/IFRS balance sheet reporting is limited to posted journals.")
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
