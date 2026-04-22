from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class OhadaBalanceSheetAccountContributionDTO:
    account_id: int
    account_code: str
    account_name: str
    account_class_code: str | None
    line_code: str | None
    line_label: str | None
    contribution_kind_code: str
    total_debit: Decimal
    total_credit: Decimal
    amount: Decimal


@dataclass(frozen=True, slots=True)
class OhadaBalanceSheetWarningDTO:
    code: str
    title: str
    message: str
    affected_line_codes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class OhadaBalanceSheetLineDTO:
    code: str
    reference_code: str | None
    label: str
    side_code: str
    section_code: str
    section_title: str
    row_kind_code: str
    display_order: int
    gross_amount: Decimal | None
    contra_amount: Decimal | None
    net_amount: Decimal | None
    can_drilldown: bool
    component_codes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class OhadaBalanceSheetLineDetailDTO:
    company_id: int
    statement_date: date | None
    line_code: str
    line_label: str
    side_code: str
    row_kind_code: str
    gross_amount: Decimal | None
    contra_amount: Decimal | None
    net_amount: Decimal | None
    accounts: tuple[OhadaBalanceSheetAccountContributionDTO, ...] = field(default_factory=tuple)
    warnings: tuple[OhadaBalanceSheetWarningDTO, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class OhadaBalanceSheetReportDTO:
    company_id: int
    statement_date: date | None
    spec_version: str
    template_code: str
    template_title: str
    asset_lines: tuple[OhadaBalanceSheetLineDTO, ...] = field(default_factory=tuple)
    liability_lines: tuple[OhadaBalanceSheetLineDTO, ...] = field(default_factory=tuple)
    warnings: tuple[OhadaBalanceSheetWarningDTO, ...] = field(default_factory=tuple)
    unclassified_accounts: tuple[OhadaBalanceSheetAccountContributionDTO, ...] = field(default_factory=tuple)
    has_chart_coverage: bool = False
    has_posted_activity: bool = False
    has_classified_activity: bool = False
    total_assets: Decimal = Decimal("0.00")
    total_liabilities_and_equity: Decimal = Decimal("0.00")
    balance_difference: Decimal = Decimal("0.00")
