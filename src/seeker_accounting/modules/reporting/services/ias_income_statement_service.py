from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.reporting.dto.ias_income_statement_dto import (
    IasIncomeStatementAccountContributionDTO,
    IasIncomeStatementLineDTO,
    IasIncomeStatementLineDetailDTO,
    IasIncomeStatementReportDTO,
)
from seeker_accounting.modules.reporting.dto.ias_income_statement_mapping_dto import (
    IasIncomeStatementMappingDTO,
    IasIncomeStatementValidationIssueDTO,
)
from seeker_accounting.modules.reporting.dto.print_preview_dto import (
    PrintPreviewMetaDTO,
    PrintPreviewRowDTO,
)
from seeker_accounting.modules.reporting.dto.reporting_filter_dto import ReportingFilterDTO
from seeker_accounting.modules.reporting.repositories.ias_income_statement_repository import (
    IasAccountActivityRow,
    IasIncomeStatementRepository,
)
from seeker_accounting.modules.reporting.services.ias_income_statement_mapping_service import (
    IasIncomeStatementMappingService,
)
from seeker_accounting.modules.reporting.services.ias_income_statement_template_service import (
    IasIncomeStatementTemplateService,
)
from seeker_accounting.modules.reporting.specs.ias_income_statement_spec import (
    IAS_INCOME_STATEMENT_PROFILE_CODE,
    IAS_SECTION_SPEC_BY_CODE,
    apply_sign_behavior,
    compute_natural_amount,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

IasIncomeStatementRepositoryFactory = Callable[[Session], IasIncomeStatementRepository]

_ZERO = Decimal("0.00")
_UNMAPPED_LINE_CODE = "UNMAPPED"
_SUMMARY_CODES = ("GROSS_PROFIT", "OPERATING_PROFIT", "PROFIT_BEFORE_TAX", "PROFIT_FOR_PERIOD")


@dataclass(frozen=True, slots=True)
class _ComputedLine:
    amount: Decimal
    contributions: tuple[IasIncomeStatementAccountContributionDTO, ...]


@dataclass(frozen=True, slots=True)
class _StatementContext:
    report: IasIncomeStatementReportDTO
    computed_lines: dict[str, _ComputedLine]
    mapping_snapshot: object
    activity_rows: tuple[IasAccountActivityRow, ...]


class IasIncomeStatementService:
    """Builds the locked IAS/IFRS income statement from posted accounting truth."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        ias_income_statement_repository_factory: IasIncomeStatementRepositoryFactory,
        ias_income_statement_mapping_service: IasIncomeStatementMappingService,
        ias_income_statement_template_service: IasIncomeStatementTemplateService,
        permission_service: PermissionService,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._ias_income_statement_repository_factory = ias_income_statement_repository_factory
        self._ias_income_statement_mapping_service = ias_income_statement_mapping_service
        self._ias_income_statement_template_service = ias_income_statement_template_service
        self._permission_service = permission_service

    def get_statement(
        self,
        filter_dto: ReportingFilterDTO,
        template_code: str | None = None,
    ) -> IasIncomeStatementReportDTO:
        self._permission_service.require_permission("reports.ias_income_statement.view")
        context = self._build_statement_context(filter_dto, template_code=template_code)
        return context.report

    def get_line_detail(
        self,
        filter_dto: ReportingFilterDTO,
        line_code: str,
    ) -> IasIncomeStatementLineDetailDTO:
        normalized_line_code = (line_code or "").strip().upper()
        context = self._build_statement_context(filter_dto)
        report = context.report
        company_id, date_from, date_to = self._normalize_filter(filter_dto)
        if normalized_line_code == _UNMAPPED_LINE_CODE:
            return IasIncomeStatementLineDetailDTO(
                company_id=company_id,
                date_from=date_from,
                date_to=date_to,
                line_code=_UNMAPPED_LINE_CODE,
                line_label="Unmapped Relevant Accounts",
                row_kind_code="support",
                signed_amount=sum(
                    (account.signed_amount for account in report.unmapped_relevant_accounts),
                    _ZERO,
                ),
                accounts=report.unmapped_relevant_accounts,
                issues=tuple(
                    issue
                    for issue in report.issues
                    if issue.issue_code == "unmapped_relevant_account"
                ),
            )

        line = next((item for item in report.lines if item.code == normalized_line_code), None)
        if line is None:
            raise NotFoundError(f"IAS line {normalized_line_code} was not found.")

        if not line.can_drilldown:
            raise ValidationError(f"IAS line {normalized_line_code} has no contributing accounts.")

        accounts = self._collect_line_accounts(context.computed_lines, normalized_line_code)
        relevant_issues = tuple(
            issue
            for issue in report.issues
            if (
                issue.section_code == normalized_line_code
                or issue.subsection_code == normalized_line_code
                or issue.account_id in {account.account_id for account in accounts}
            )
        )
        return IasIncomeStatementLineDetailDTO(
            company_id=company_id,
            date_from=date_from,
            date_to=date_to,
            line_code=line.code,
            line_label=line.label,
            row_kind_code=line.row_kind_code,
            signed_amount=line.signed_amount or _ZERO,
            accounts=accounts,
            issues=relevant_issues,
        )

    def list_unmapped_accounts(self, filter_dto: ReportingFilterDTO) -> IasIncomeStatementLineDetailDTO:
        return self.get_line_detail(filter_dto, _UNMAPPED_LINE_CODE)

    def build_print_preview_meta(
        self,
        report_dto: IasIncomeStatementReportDTO,
        company_name: str,
    ) -> PrintPreviewMetaDTO:
        period_label = self._format_period_label(report_dto.date_from, report_dto.date_to)
        filter_summary = self._build_filter_summary(report_dto)
        return PrintPreviewMetaDTO(
            report_title="IAS Income Statement Builder",
            company_name=company_name,
            period_label=period_label,
            generated_at=self._generated_at(),
            filter_summary=filter_summary,
            template_title=report_dto.template_title,
            rows=tuple(self._build_preview_rows(report_dto)),
        )

    def _build_leaf_contributions(
        self,
        *,
        active_mappings: dict[int, IasIncomeStatementMappingDTO],
        activity_map: dict[int, IasAccountActivityRow],
        section_map: dict[str, object],
        mapping_issues: tuple[IasIncomeStatementValidationIssueDTO, ...],
    ) -> dict[str, dict[int, IasIncomeStatementAccountContributionDTO]]:
        contributions_by_leaf_code: dict[str, dict[int, IasIncomeStatementAccountContributionDTO]] = defaultdict(dict)

        for account_id, mapping in active_mappings.items():
            if not self._is_reportable_mapping(mapping, section_map):
                continue
            activity = activity_map.get(account_id)
            if mapping.account_code == "" or mapping.account_name == "":
                continue
            debit_amount = activity.total_debit if activity is not None else _ZERO
            credit_amount = activity.total_credit if activity is not None else _ZERO
            natural_amount = compute_natural_amount(
                total_debit=debit_amount,
                total_credit=credit_amount,
                normal_balance=mapping.normal_balance,
            )
            signed_amount = apply_sign_behavior(natural_amount, mapping.sign_behavior_code)
            leaf_code = mapping.subsection_code or mapping.section_code

            contributions_by_leaf_code[leaf_code][account_id] = IasIncomeStatementAccountContributionDTO(
                mapping_id=mapping.id,
                account_id=account_id,
                account_code=mapping.account_code or f"#{account_id}",
                account_name=mapping.account_name or "Missing account",
                account_class_code=mapping.account_class_code,
                account_type_code=mapping.account_type_code,
                account_type_section_code=mapping.account_type_section_code,
                normal_balance=mapping.normal_balance,
                section_code=mapping.section_code,
                section_label=mapping.section_label,
                subsection_code=mapping.subsection_code,
                subsection_label=mapping.subsection_label,
                sign_behavior_code=mapping.sign_behavior_code,
                default_sign_behavior_code=mapping.default_sign_behavior_code,
                debit_amount=debit_amount,
                credit_amount=credit_amount,
                natural_amount=natural_amount,
                signed_amount=signed_amount,
                account_is_active=mapping.account_is_active,
                allow_manual_posting=mapping.allow_manual_posting,
                is_control_account=mapping.is_control_account,
            )

        return contributions_by_leaf_code

    @staticmethod
    def _is_reportable_mapping(
        mapping: IasIncomeStatementMappingDTO,
        section_map: dict[str, object],
    ) -> bool:
        if not mapping.account_is_active or not mapping.allow_manual_posting:
            return False

        section = section_map.get(mapping.section_code)
        if section is None:
            return False
        if getattr(section, "row_kind_code", None) == "formula":
            return False
        if not getattr(section, "is_mapping_target", False) and getattr(section, "row_kind_code", None) != "group":
            return False

        subsection_code = (mapping.subsection_code or "").strip().upper()
        if subsection_code:
            subsection = section_map.get(subsection_code)
            if subsection is None:
                return False
            if getattr(subsection, "parent_section_code", None) != mapping.section_code:
                return False
            if getattr(subsection, "row_kind_code", None) == "formula":
                return False
            if not getattr(subsection, "is_mapping_target", False):
                return False
        elif getattr(section, "row_kind_code", None) == "group":
            return False

        return True

    def _compute_lines(
        self,
        leaf_contributions: dict[str, dict[int, IasIncomeStatementAccountContributionDTO]],
    ) -> dict[str, _ComputedLine]:
        cache: dict[str, _ComputedLine] = {}
        section_map = {section.section_code: section for section in self._ias_income_statement_template_service.list_sections()}

        def resolve(section_code: str) -> _ComputedLine:
            if section_code in cache:
                return cache[section_code]
            section = section_map[section_code]

            if section.is_formula:
                contributions: dict[int, IasIncomeStatementAccountContributionDTO] = {}
                amount = _ZERO
                for component_code in section.formula_components:
                    component = resolve(component_code)
                    amount += component.amount
                    self._merge_contributions(contributions, self._contributions_to_dict(component.contributions))
                cache[section_code] = _ComputedLine(amount=amount, contributions=self._sorted_contributions(contributions))
                return cache[section_code]

            if section.row_kind_code == "group":
                contributions = {}
                amount = _ZERO
                for component_code in section.aggregation_components:
                    component = resolve(component_code)
                    amount += component.amount
                    self._merge_contributions(contributions, self._contributions_to_dict(component.contributions))
                cache[section_code] = _ComputedLine(amount=amount, contributions=self._sorted_contributions(contributions))
                return cache[section_code]

            leaf_map = leaf_contributions.get(section_code, {})
            amount = sum((contribution.signed_amount for contribution in leaf_map.values()), _ZERO)
            cache[section_code] = _ComputedLine(
                amount=amount,
                contributions=self._sorted_contributions(dict(leaf_map)),
            )
            return cache[section_code]

        for section_code in section_map:
            resolve(section_code)
        return cache

    def _build_unmapped_accounts(
        self,
        *,
        company_id: int,
        activity_rows: list[IasAccountActivityRow],
        mapping_snapshot,
    ) -> tuple[IasIncomeStatementAccountContributionDTO, ...]:
        mapped_account_ids = {
            mapping.account_id
            for mapping in mapping_snapshot.mappings
            if mapping.is_active and mapping.account_id is not None
        }
        activity_map = {row.account_id: row for row in activity_rows}
        unmapped_accounts: list[IasIncomeStatementAccountContributionDTO] = []
        for account in mapping_snapshot.account_options:
            if account.account_id in mapped_account_ids:
                continue
            if not account.is_active:
                continue
            if account.mapped_mapping_id is not None and account.mapped_is_active is True:
                continue
            if not self._is_relevant_unmapped_account(account):
                continue
            activity = activity_map.get(account.account_id)
            debit_amount = activity.total_debit if activity is not None else _ZERO
            credit_amount = activity.total_credit if activity is not None else _ZERO
            natural_amount = compute_natural_amount(
                total_debit=debit_amount,
                total_credit=credit_amount,
                normal_balance=account.normal_balance,
            )
            signed_amount = apply_sign_behavior(
                natural_amount,
                account.default_sign_behavior_code,
            )
            unmapped_accounts.append(
                IasIncomeStatementAccountContributionDTO(
                    mapping_id=0,
                    account_id=account.account_id,
                    account_code=account.account_code,
                    account_name=account.account_name,
                    account_class_code=account.account_class_code,
                    account_type_code=account.account_type_code,
                    account_type_section_code=account.account_type_section_code,
                    normal_balance=account.normal_balance,
                    section_code="UNMAPPED",
                    section_label="Unmapped Relevant Account",
                    subsection_code=None,
                    subsection_label=None,
                    sign_behavior_code=account.default_sign_behavior_code,
                    default_sign_behavior_code=account.default_sign_behavior_code,
                    debit_amount=debit_amount,
                    credit_amount=credit_amount,
                    natural_amount=natural_amount,
                    signed_amount=signed_amount,
                    account_is_active=account.is_active,
                    allow_manual_posting=account.allow_manual_posting,
                    is_control_account=account.is_control_account,
                )
            )
        return tuple(sorted(unmapped_accounts, key=lambda value: (value.account_code, value.account_id)))

    @staticmethod
    def _is_relevant_unmapped_account(account: object) -> bool:
        account_class_code = getattr(account, "account_class_code", None)
        account_type_section_code = getattr(account, "account_type_section_code", None)
        account_code = getattr(account, "account_code", "")
        if account_class_code in {"6", "7", "8"}:
            return True
        if (account_type_section_code or "").strip().upper() in {"REVENUE", "EXPENSE"}:
            return True
        return str(account_code or "").startswith(("6", "7", "8"))

    def _collect_line_accounts(
        self,
        computed_lines: dict[str, _ComputedLine],
        line_code: str,
    ) -> tuple[IasIncomeStatementAccountContributionDTO, ...]:
        computed = computed_lines.get(line_code)
        if computed is None:
            return ()
        return computed.contributions

    def _merge_contributions(
        self,
        target: dict[int, IasIncomeStatementAccountContributionDTO],
        source: dict[int, IasIncomeStatementAccountContributionDTO],
    ) -> None:
        for account_id, contribution in source.items():
            existing = target.get(account_id)
            if existing is None:
                target[account_id] = contribution
                continue
            target[account_id] = IasIncomeStatementAccountContributionDTO(
                mapping_id=existing.mapping_id,
                account_id=existing.account_id,
                account_code=existing.account_code,
                account_name=existing.account_name,
                account_class_code=existing.account_class_code,
                account_type_code=existing.account_type_code,
                account_type_section_code=existing.account_type_section_code,
                normal_balance=existing.normal_balance,
                section_code=existing.section_code,
                section_label=existing.section_label,
                subsection_code=existing.subsection_code,
                subsection_label=existing.subsection_label,
                sign_behavior_code=existing.sign_behavior_code,
                default_sign_behavior_code=existing.default_sign_behavior_code,
                debit_amount=existing.debit_amount + contribution.debit_amount,
                credit_amount=existing.credit_amount + contribution.credit_amount,
                natural_amount=existing.natural_amount + contribution.natural_amount,
                signed_amount=existing.signed_amount + contribution.signed_amount,
                account_is_active=existing.account_is_active,
                allow_manual_posting=existing.allow_manual_posting,
                is_control_account=existing.is_control_account,
            )

    @staticmethod
    def _contributions_to_dict(
        contributions: tuple[IasIncomeStatementAccountContributionDTO, ...],
    ) -> dict[int, IasIncomeStatementAccountContributionDTO]:
        return {c.account_id: c for c in contributions}

    def _sorted_contributions(
        self,
        contribution_map: dict[int, IasIncomeStatementAccountContributionDTO],
    ) -> tuple[IasIncomeStatementAccountContributionDTO, ...]:
        return tuple(
            sorted(
                contribution_map.values(),
                key=lambda value: (value.account_code, value.account_id),
            )
        )

    def _resolve_active_mappings(
        self,
        mappings: tuple[IasIncomeStatementMappingDTO, ...],
    ) -> dict[int, IasIncomeStatementMappingDTO]:
        resolved: dict[int, IasIncomeStatementMappingDTO] = {}
        for mapping in sorted(
            mappings,
            key=lambda value: (not value.is_active, value.display_order, value.id),
        ):
            if not mapping.is_active:
                continue
            if mapping.account_id in resolved:
                continue
            resolved[mapping.account_id] = mapping
        return resolved

    def _build_statement_context(
        self,
        filter_dto: ReportingFilterDTO,
        template_code: str | None = None,
    ) -> _StatementContext:
        company_id, date_from, date_to = self._normalize_filter(filter_dto)
        template = self._ias_income_statement_template_service.get_template(template_code)

        with self._unit_of_work_factory() as uow:
            repo = self._ias_income_statement_repository_factory(uow.session)
            activity_rows = tuple(repo.list_period_activity(company_id, date_from, date_to))

        mapping_snapshot = self._ias_income_statement_mapping_service.get_editor_snapshot(company_id)
        active_mappings = tuple(mapping for mapping in mapping_snapshot.mappings if mapping.is_active)
        active_mappings_by_account_id = self._resolve_active_mappings(active_mappings)
        activity_map = {row.account_id: row for row in activity_rows}
        section_map = self._ias_income_statement_template_service.get_section_map()

        leaf_contributions = self._build_leaf_contributions(
            active_mappings=active_mappings_by_account_id,
            activity_map=activity_map,
            section_map=section_map,
            mapping_issues=mapping_snapshot.issues,
        )
        computed_lines = self._compute_lines(leaf_contributions)

        issues = tuple(
            issue
            for issue in mapping_snapshot.issues
            if issue.severity_code in {"error", "warning"}
        )

        sections = self._ias_income_statement_template_service.list_sections()
        report_lines: list[IasIncomeStatementLineDTO] = []
        for section in sections:
            computed = computed_lines.get(section.section_code)
            report_lines.append(
                IasIncomeStatementLineDTO(
                    code=section.section_code,
                    label=section.section_label,
                    row_kind_code=section.row_kind_code,
                    parent_code=section.parent_section_code,
                    display_order=section.display_order,
                    indent_level=section.indent_level,
                    signed_amount=computed.amount if computed is not None else _ZERO,
                    can_drilldown=bool(computed and computed.contributions),
                    is_formula=section.is_formula,
                    is_mapping_target=section.is_mapping_target,
                    aggregation_components=IAS_SECTION_SPEC_BY_CODE[section.section_code].aggregation_components,
                    formula_components=IAS_SECTION_SPEC_BY_CODE[section.section_code].formula_components,
                )
            )

        unmapped_accounts = self._build_unmapped_accounts(
            company_id=company_id,
            activity_rows=activity_rows,
            mapping_snapshot=mapping_snapshot,
        )

        has_mappings = bool(active_mappings)
        has_posted_activity = bool(activity_rows)
        has_unmapped_accounts = bool(unmapped_accounts)
        has_validation_issues = bool(issues)

        if not has_mappings:
            issues = issues + (
                IasIncomeStatementValidationIssueDTO(
                    issue_code="no_mappings",
                    severity_code="info",
                    title="No IAS mappings yet",
                    message=(
                        "No active IAS account mappings exist for this company. Use Manage Mappings "
                        "to assign accounts to the locked IAS sections."
                    ),
                ),
            )
        if has_mappings and not has_posted_activity:
            issues = issues + (
                IasIncomeStatementValidationIssueDTO(
                    issue_code="no_posted_activity",
                    severity_code="info",
                    title="No posted activity in scope",
                    message=(
                        "The selected reporting period has no posted journal activity for the IAS statement."
                    ),
                ),
            )

        report = IasIncomeStatementReportDTO(
            company_id=company_id,
            date_from=date_from,
            date_to=date_to,
            statement_profile_code=IAS_INCOME_STATEMENT_PROFILE_CODE,
            template_code=template.template_code,
            template_title=template.template_title,
            lines=tuple(report_lines),
            issues=issues,
            unmapped_relevant_accounts=unmapped_accounts,
            has_mappings=has_mappings,
            has_posted_activity=has_posted_activity,
            has_unmapped_accounts=has_unmapped_accounts,
            has_validation_issues=has_validation_issues or not has_mappings or not has_posted_activity,
            summary_line_codes=_SUMMARY_CODES,
        )
        return _StatementContext(
            report=report,
            computed_lines=computed_lines,
            mapping_snapshot=mapping_snapshot,
            activity_rows=activity_rows,
        )

    def _build_preview_rows(
        self,
        report_dto: IasIncomeStatementReportDTO,
    ) -> list[PrintPreviewRowDTO]:
        rows: list[PrintPreviewRowDTO] = []
        for line in report_dto.lines:
            indent = "    " * line.indent_level
            if line.row_kind_code == "group":
                rows.append(
                    PrintPreviewRowDTO(
                        row_type="section",
                        reference_code=None,
                        label=f"{indent}{line.label}",
                        amount_text=self._fmt(line.signed_amount),
                    )
                )
                continue
            rows.append(
                PrintPreviewRowDTO(
                    row_type="subtotal" if line.is_formula else "line",
                    reference_code=line.code,
                    label=f"{indent}{line.label}",
                    amount_text=self._fmt(line.signed_amount),
                )
            )
        return rows

    def _build_filter_summary(self, report_dto: IasIncomeStatementReportDTO) -> str:
        parts = [f"Template: {report_dto.template_title}"]
        parts.append(f"Mapped: {'Yes' if report_dto.has_mappings else 'No'}")
        parts.append(f"Unmapped: {len(report_dto.unmapped_relevant_accounts)}")
        if report_dto.has_validation_issues:
            parts.append("Validation warnings present")
        return " · ".join(parts)

    def _format_period_label(self, date_from: date | None, date_to: date | None) -> str:
        if date_from is None and date_to is None:
            return "All periods"
        if date_from is None:
            return f"Up to {date_to.strftime('%d %b %Y')}" if date_to is not None else "All periods"
        if date_to is None:
            return f"From {date_from.strftime('%d %b %Y')}"
        return f"{date_from.strftime('%d %b %Y')} - {date_to.strftime('%d %b %Y')}"

    def _normalize_filter(self, filter_dto: ReportingFilterDTO) -> tuple[int, date | None, date | None]:
        company_id = filter_dto.company_id
        if not isinstance(company_id, int) or company_id <= 0:
            raise ValidationError("Select an active company to run the IAS/IFRS income statement.")
        if not filter_dto.posted_only:
            raise ValidationError("IAS/IFRS income statement reporting is limited to posted journals.")

        date_from = filter_dto.date_from
        date_to = filter_dto.date_to
        if date_from and date_to and date_to < date_from:
            raise ValidationError("The 'To' date must be on or after the 'From' date.")
        return company_id, date_from, date_to

    @staticmethod
    def _fmt(amount: Decimal | None) -> str:
        value = amount or _ZERO
        if value == _ZERO:
            return "0.00"
        return f"{value:,.2f}"

    @staticmethod
    def _generated_at() -> str:
        from datetime import datetime

        return datetime.now().strftime("%Y-%m-%d %H:%M")
