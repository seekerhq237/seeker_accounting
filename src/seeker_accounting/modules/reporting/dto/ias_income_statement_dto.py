from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from seeker_accounting.modules.reporting.dto.ias_income_statement_mapping_dto import (
    IasIncomeStatementValidationIssueDTO,
)


@dataclass(frozen=True, slots=True)
class IasIncomeStatementAccountContributionDTO:
    mapping_id: int
    account_id: int
    account_code: str
    account_name: str
    account_class_code: str | None
    account_type_code: str | None
    account_type_section_code: str | None
    normal_balance: str
    section_code: str
    section_label: str
    subsection_code: str | None
    subsection_label: str | None
    sign_behavior_code: str
    default_sign_behavior_code: str
    debit_amount: Decimal
    credit_amount: Decimal
    natural_amount: Decimal
    signed_amount: Decimal
    account_is_active: bool
    allow_manual_posting: bool
    is_control_account: bool


@dataclass(frozen=True, slots=True)
class IasIncomeStatementLineDTO:
    code: str
    label: str
    row_kind_code: str
    parent_code: str | None
    display_order: int
    indent_level: int
    signed_amount: Decimal | None
    can_drilldown: bool
    is_formula: bool
    is_mapping_target: bool
    aggregation_components: tuple[str, ...] = ()
    formula_components: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class IasIncomeStatementLineDetailDTO:
    company_id: int
    date_from: date | None
    date_to: date | None
    line_code: str
    line_label: str
    row_kind_code: str
    signed_amount: Decimal
    accounts: tuple[IasIncomeStatementAccountContributionDTO, ...]
    issues: tuple[IasIncomeStatementValidationIssueDTO, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class IasIncomeStatementReportDTO:
    company_id: int
    date_from: date | None
    date_to: date | None
    statement_profile_code: str
    template_code: str
    template_title: str
    lines: tuple[IasIncomeStatementLineDTO, ...]
    issues: tuple[IasIncomeStatementValidationIssueDTO, ...]
    unmapped_relevant_accounts: tuple[IasIncomeStatementAccountContributionDTO, ...] = field(default_factory=tuple)
    has_mappings: bool = False
    has_posted_activity: bool = False
    has_unmapped_accounts: bool = False
    has_validation_issues: bool = False
    summary_line_codes: tuple[str, ...] = field(default_factory=tuple)

