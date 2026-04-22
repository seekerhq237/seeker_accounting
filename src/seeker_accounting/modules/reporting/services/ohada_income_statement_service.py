from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.reporting.dto.ohada_income_statement_dto import (
    OhadaAccountContributionDTO,
    OhadaCoverageWarningDTO,
    OhadaIncomeStatementLineDTO,
    OhadaIncomeStatementLineDetailDTO,
    OhadaIncomeStatementReportDTO,
)
from seeker_accounting.modules.reporting.dto.reporting_filter_dto import ReportingFilterDTO
from seeker_accounting.modules.reporting.repositories.ohada_income_statement_repository import (
    OhadaAccountActivityRow,
    OhadaChartAccountRow,
    OhadaIncomeStatementRepository,
)
from seeker_accounting.modules.reporting.specs.ohada_income_statement_spec import (
    OHADA_ALL_PREFIXES,
    OHADA_BASE_LINE_SPEC_BY_CODE,
    OHADA_BASE_LINE_SPECS,
    OHADA_FORMULA_LINE_SPECS,
    OHADA_INCOME_STATEMENT_VERSION,
    OHADA_LINE_SPECS,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

OhadaIncomeStatementRepositoryFactory = Callable[[Session], OhadaIncomeStatementRepository]

_ZERO = Decimal("0.00")
_UNCLASSIFIED_LINE_CODE = "UNCLASSIFIED"


@dataclass(frozen=True, slots=True)
class _LineComputation:
    spec_code: str
    signed_amount: Decimal
    accounts: tuple[OhadaAccountContributionDTO, ...]


class OhadaIncomeStatementService:
    """Builds the locked OHADA income statement from posted accounting truth."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        ohada_income_statement_repository_factory: OhadaIncomeStatementRepositoryFactory,
        permission_service: PermissionService,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._ohada_income_statement_repository_factory = ohada_income_statement_repository_factory
        self._permission_service = permission_service

    def get_statement(self, filter_dto: ReportingFilterDTO) -> OhadaIncomeStatementReportDTO:
        self._permission_service.require_permission("reports.ohada_income_statement.view")
        company_id, date_from, date_to = self._normalize_filter(filter_dto)
        with self._unit_of_work_factory() as uow:
            repo = self._ohada_income_statement_repository_factory(uow.session)
            activity_rows = repo.list_period_activity(company_id, date_from, date_to)
            chart_rows = repo.list_company_profit_and_loss_accounts(company_id)

        computed = self._compute_lines(activity_rows)
        warnings, unclassified_accounts, has_chart_coverage = self._build_warnings(
            chart_rows=chart_rows,
            activity_rows=activity_rows,
            computed=computed,
        )

        lines = tuple(
            OhadaIncomeStatementLineDTO(
                code=spec.code,
                label=spec.label,
                section_code=spec.section_code,
                section_title=spec.section_title,
                signed_amount=computed[spec.code].signed_amount,
                display_order=spec.display_order,
                is_formula=spec.is_formula,
                can_drilldown=bool(computed[spec.code].accounts),
                prefixes=spec.prefixes,
                formula_components=spec.formula_components,
            )
            for spec in OHADA_LINE_SPECS
        )

        has_posted_activity = bool(activity_rows)
        has_classified_activity = any(
            detail.signed_amount != _ZERO
            for code, detail in computed.items()
            if code in OHADA_BASE_LINE_SPEC_BY_CODE
        )

        highlight_line_codes = tuple(
            code
            for code in ("XA", "XB", "XC", "XD", "XE", "XF", "XG", "XH", "XI")
            if code in computed
        )

        return OhadaIncomeStatementReportDTO(
            company_id=company_id,
            date_from=date_from,
            date_to=date_to,
            spec_version=OHADA_INCOME_STATEMENT_VERSION,
            lines=lines,
            warnings=warnings,
            unclassified_accounts=unclassified_accounts,
            has_chart_coverage=has_chart_coverage,
            has_posted_activity=has_posted_activity,
            has_classified_activity=has_classified_activity,
            highlight_line_codes=highlight_line_codes,
        )

    def get_line_detail(
        self,
        filter_dto: ReportingFilterDTO,
        line_code: str,
    ) -> OhadaIncomeStatementLineDetailDTO:
        normalized_code = (line_code or "").strip().upper()
        company_id, date_from, date_to = self._normalize_filter(filter_dto)
        with self._unit_of_work_factory() as uow:
            repo = self._ohada_income_statement_repository_factory(uow.session)
            activity_rows = repo.list_period_activity(company_id, date_from, date_to)
            chart_rows = repo.list_company_profit_and_loss_accounts(company_id)

        computed = self._compute_lines(activity_rows)
        warnings, unclassified_accounts, _ = self._build_warnings(
            chart_rows=chart_rows,
            activity_rows=activity_rows,
            computed=computed,
        )

        if normalized_code == _UNCLASSIFIED_LINE_CODE:
            return OhadaIncomeStatementLineDetailDTO(
                company_id=company_id,
                date_from=date_from,
                date_to=date_to,
                line_code=_UNCLASSIFIED_LINE_CODE,
                line_label="Unclassified OHADA Accounts",
                signed_amount=sum((account.signed_amount for account in unclassified_accounts), _ZERO),
                accounts=unclassified_accounts,
                warnings=tuple(
                    warning for warning in warnings if warning.code == "unclassified_activity"
                ),
            )

        detail = computed.get(normalized_code)
        if detail is None:
            raise NotFoundError(f"OHADA line {normalized_code} was not found.")

        spec = next(spec for spec in OHADA_LINE_SPECS if spec.code == normalized_code)
        return OhadaIncomeStatementLineDetailDTO(
            company_id=company_id,
            date_from=date_from,
            date_to=date_to,
            line_code=spec.code,
            line_label=spec.label,
            signed_amount=detail.signed_amount,
            accounts=detail.accounts,
            warnings=tuple(
                warning
                for warning in warnings
                if normalized_code in warning.affected_line_codes
            ),
        )

    def list_unclassified_accounts(self, filter_dto: ReportingFilterDTO) -> OhadaIncomeStatementLineDetailDTO:
        return self.get_line_detail(filter_dto, _UNCLASSIFIED_LINE_CODE)

    def _compute_lines(self, activity_rows: list[OhadaAccountActivityRow]) -> dict[str, _LineComputation]:
        base_accounts_by_code: dict[str, list[OhadaAccountContributionDTO]] = defaultdict(list)
        for row in activity_rows:
            matched_code = self._match_base_line_code(row.account_code)
            if matched_code is None:
                continue
            spec = OHADA_BASE_LINE_SPEC_BY_CODE[matched_code]
            base_accounts_by_code[matched_code].append(
                OhadaAccountContributionDTO(
                    account_id=row.account_id,
                    account_code=row.account_code,
                    account_name=row.account_name,
                    account_class_code=row.account_class_code,
                    line_code=spec.code,
                    line_label=spec.label,
                    debit_amount=row.total_debit,
                    credit_amount=row.total_credit,
                    signed_amount=row.total_credit - row.total_debit,
                )
            )

        computed: dict[str, _LineComputation] = {}
        for spec in OHADA_BASE_LINE_SPECS:
            accounts = tuple(
                sorted(
                    base_accounts_by_code.get(spec.code, ()),
                    key=lambda account: (account.account_code, account.account_id),
                )
            )
            computed[spec.code] = _LineComputation(
                spec_code=spec.code,
                signed_amount=sum((account.signed_amount for account in accounts), _ZERO),
                accounts=accounts,
            )

        for spec in OHADA_FORMULA_LINE_SPECS:
            component_accounts: dict[int, OhadaAccountContributionDTO] = {}
            amount = _ZERO
            for component_code in spec.formula_components:
                component = computed[component_code]
                amount += component.signed_amount
                for account in component.accounts:
                    existing = component_accounts.get(account.account_id)
                    if existing is None:
                        component_accounts[account.account_id] = account
                        continue
                    component_accounts[account.account_id] = OhadaAccountContributionDTO(
                        account_id=existing.account_id,
                        account_code=existing.account_code,
                        account_name=existing.account_name,
                        account_class_code=existing.account_class_code,
                        line_code=existing.line_code,
                        line_label=existing.line_label,
                        debit_amount=existing.debit_amount + account.debit_amount,
                        credit_amount=existing.credit_amount + account.credit_amount,
                        signed_amount=existing.signed_amount + account.signed_amount,
                    )

            computed[spec.code] = _LineComputation(
                spec_code=spec.code,
                signed_amount=amount,
                accounts=tuple(
                    sorted(
                        component_accounts.values(),
                        key=lambda account: (
                            account.line_code or "",
                            account.account_code,
                            account.account_id,
                        ),
                    )
                ),
            )

        return computed

    def _build_warnings(
        self,
        *,
        chart_rows: list[OhadaChartAccountRow],
        activity_rows: list[OhadaAccountActivityRow],
        computed: dict[str, _LineComputation],
    ) -> tuple[tuple[OhadaCoverageWarningDTO, ...], tuple[OhadaAccountContributionDTO, ...], bool]:
        warnings: list[OhadaCoverageWarningDTO] = []

        matched_prefixes = {
            prefix
            for row in chart_rows
            for prefix in OHADA_ALL_PREFIXES
            if row.account_code.startswith(prefix)
        }
        has_chart_coverage = bool(matched_prefixes)

        missing_line_codes = tuple(
            spec.code
            for spec in OHADA_BASE_LINE_SPECS
            if not any(
                row.account_code.startswith(prefix)
                for row in chart_rows
                for prefix in spec.prefixes
            )
        )
        if missing_line_codes:
            warnings.append(
                OhadaCoverageWarningDTO(
                    code="missing_prefix_coverage",
                    title="Incomplete OHADA chart coverage",
                    message=(
                        "Some locked OHADA line prefixes are not present in the company chart. "
                        "Those lines stay at zero until the chart is completed."
                    ),
                    affected_line_codes=missing_line_codes,
                )
            )

        unclassified_accounts = tuple(
            sorted(
                (
                    OhadaAccountContributionDTO(
                        account_id=row.account_id,
                        account_code=row.account_code,
                        account_name=row.account_name,
                        account_class_code=row.account_class_code,
                        line_code=None,
                        line_label=None,
                        debit_amount=row.total_debit,
                        credit_amount=row.total_credit,
                        signed_amount=row.total_credit - row.total_debit,
                    )
                    for row in activity_rows
                    if self._is_profit_and_loss_account(row.account_code, row.account_class_code)
                    and self._match_base_line_code(row.account_code) is None
                ),
                key=lambda account: (account.account_code, account.account_id),
            )
        )
        if unclassified_accounts:
            warnings.append(
                OhadaCoverageWarningDTO(
                    code="unclassified_activity",
                    title="Unclassified OHADA activity detected",
                    message=(
                        "Some posted profit-and-loss accounts fall outside the locked OHADA prefixes. "
                        "They are excluded from statement lines and should be reviewed."
                    ),
                )
            )

        if chart_rows and not any(
            detail.signed_amount != _ZERO
            for code, detail in computed.items()
            if code in OHADA_BASE_LINE_SPEC_BY_CODE
        ) and not unclassified_accounts:
            warnings.append(
                OhadaCoverageWarningDTO(
                    code="no_posted_activity",
                    title="No posted OHADA activity in scope",
                    message=(
                        "The selected period has no posted activity across the locked OHADA "
                        "income statement prefixes."
                    ),
                )
            )

        if not has_chart_coverage:
            warnings.append(
                OhadaCoverageWarningDTO(
                    code="no_ohada_chart_coverage",
                    title="No OHADA chart coverage detected",
                    message=(
                        "No company chart accounts were found under the locked OHADA income "
                        "statement prefixes. Seed or review the company chart before relying "
                        "on this statement."
                    ),
                )
            )

        return tuple(warnings), unclassified_accounts, has_chart_coverage

    def _normalize_filter(self, filter_dto: ReportingFilterDTO) -> tuple[int, date | None, date | None]:
        company_id = filter_dto.company_id
        if not isinstance(company_id, int) or company_id <= 0:
            raise ValidationError("Select an active company to run the OHADA income statement.")
        if not filter_dto.posted_only:
            raise ValidationError("OHADA income statement reporting is limited to posted journals.")

        date_from = filter_dto.date_from
        date_to = filter_dto.date_to
        if date_from and date_to and date_to < date_from:
            raise ValidationError("The 'To' date must be on or after the 'From' date.")
        return company_id, date_from, date_to

    @staticmethod
    def _match_base_line_code(account_code: str) -> str | None:
        normalized = (account_code or "").strip()
        if not normalized:
            return None
        ordered_specs = sorted(
            OHADA_BASE_LINE_SPECS,
            key=lambda spec: max((len(prefix) for prefix in spec.prefixes), default=0),
            reverse=True,
        )
        for spec in ordered_specs:
            if any(normalized.startswith(prefix) for prefix in spec.prefixes):
                return spec.code
        return None

    @staticmethod
    def _is_profit_and_loss_account(account_code: str, account_class_code: str | None) -> bool:
        if account_class_code in {"6", "7", "8"}:
            return True
        normalized = (account_code or "").strip()
        return normalized.startswith(("6", "7", "8"))
