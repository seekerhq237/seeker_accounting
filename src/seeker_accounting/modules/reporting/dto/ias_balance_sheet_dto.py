from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class IasBalanceSheetAccountContributionDTO:
    account_id: int
    account_code: str
    account_name: str
    account_class_code: str | None
    account_type_code: str | None
    account_type_section_code: str | None
    normal_balance: str
    line_code: str
    line_label: str
    contribution_kind_code: str
    total_debit: Decimal
    total_credit: Decimal
    amount: Decimal
    account_is_active: bool
    allow_manual_posting: bool
    is_control_account: bool


@dataclass(frozen=True, slots=True)
class IasBalanceSheetWarningDTO:
    code: str
    severity_code: str
    title: str
    message: str
    affected_line_codes: tuple[str, ...] = field(default_factory=tuple)
    account_id: int | None = None


@dataclass(frozen=True, slots=True)
class IasBalanceSheetLineDTO:
    code: str
    label: str
    row_kind_code: str
    parent_code: str | None
    display_order: int
    indent_level: int
    amount: Decimal | None
    can_drilldown: bool
    is_formula: bool
    is_classification_target: bool
    aggregation_components: tuple[str, ...] = field(default_factory=tuple)
    formula_components: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class IasBalanceSheetLineDetailDTO:
    company_id: int
    statement_date: date | None
    line_code: str
    line_label: str
    row_kind_code: str
    amount: Decimal
    accounts: tuple[IasBalanceSheetAccountContributionDTO, ...] = field(default_factory=tuple)
    warnings: tuple[IasBalanceSheetWarningDTO, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class IasBalanceSheetReportDTO:
    company_id: int
    statement_date: date | None
    spec_version: str
    template_code: str
    template_title: str
    lines: tuple[IasBalanceSheetLineDTO, ...] = field(default_factory=tuple)
    warnings: tuple[IasBalanceSheetWarningDTO, ...] = field(default_factory=tuple)
    unclassified_accounts: tuple[IasBalanceSheetAccountContributionDTO, ...] = field(default_factory=tuple)
    has_posted_activity: bool = False
    has_classified_activity: bool = False
    total_assets: Decimal = Decimal("0.00")
    total_equity_and_liabilities: Decimal = Decimal("0.00")
    balance_difference: Decimal = Decimal("0.00")
