from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class DashboardKpiDTO:
    """Top-level KPI values for the dashboard strip."""

    cash_position: Decimal = Decimal("0.00")
    receivables_due: Decimal = Decimal("0.00")
    payables_due: Decimal = Decimal("0.00")
    month_revenue: Decimal | None = None
    month_expenses: Decimal | None = None
    pending_postings: int = 0
    currency_code: str = ""


@dataclass(frozen=True, slots=True)
class DashboardRecentActivityItemDTO:
    """A single row in the Recent Activity table."""

    entry_date: date
    document_number: str
    description: str
    amount: Decimal
    status_code: str
    document_type: str  # "journal" | "invoice" | "bill" | "receipt" | "payment"
    nav_id: str
    record_id: int


@dataclass(frozen=True, slots=True)
class DashboardAttentionItemDTO:
    """A single item in the Tasks Requiring Attention list."""

    label: str
    count: int
    severity: str  # "info" | "warning" | "danger"
    nav_id: str
    icon_hint: str  # e.g. "journal", "invoice", "bill", "bank", "inventory"


@dataclass(frozen=True, slots=True)
class DashboardAgingSnapshotDTO:
    """Aging bucket totals for AR or AP."""

    current: Decimal = Decimal("0.00")
    bucket_1_30: Decimal = Decimal("0.00")
    bucket_31_60: Decimal = Decimal("0.00")
    bucket_61_90: Decimal = Decimal("0.00")
    bucket_91_plus: Decimal = Decimal("0.00")
    grand_total: Decimal = Decimal("0.00")


@dataclass(frozen=True, slots=True)
class DashboardCashAccountRowDTO:
    """Balance for a single financial account shown on the Cash & Liquidity tab."""

    account_name: str
    account_code: str
    account_type_code: str  # e.g. "bank", "cash", "mobile_money"
    closing_balance: Decimal


@dataclass(frozen=True, slots=True)
class DashboardCashTrendPointDTO:
    """A single day's aggregated inflow/outflow for the cash trend chart."""

    as_of: date
    inflow: Decimal = Decimal("0.00")
    outflow: Decimal = Decimal("0.00")


@dataclass(frozen=True, slots=True)
class DashboardCashLiquidityDTO:
    """Aggregated cash and liquidity data for the Cash & Liquidity dashboard tab."""

    accounts: tuple[DashboardCashAccountRowDTO, ...] = field(default_factory=tuple)
    total_balance: Decimal = Decimal("0.00")
    total_inflow: Decimal = Decimal("0.00")
    total_outflow: Decimal = Decimal("0.00")
    period_label: str = ""
    trend_points: tuple[DashboardCashTrendPointDTO, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class DashboardKpiDeltaDTO:
    """Month-over-month deltas shown as trend chips on the KPI strip."""

    cash_position_delta_pct: Decimal | None = None
    receivables_delta_pct: Decimal | None = None
    payables_delta_pct: Decimal | None = None
    revenue_delta_pct: Decimal | None = None
    expenses_delta_pct: Decimal | None = None


@dataclass(frozen=True, slots=True)
class DashboardDataDTO:
    """Composite object carrying all dashboard surface data."""

    kpis: DashboardKpiDTO = field(default_factory=DashboardKpiDTO)
    kpi_deltas: DashboardKpiDeltaDTO = field(default_factory=DashboardKpiDeltaDTO)
    recent_activity: tuple[DashboardRecentActivityItemDTO, ...] = field(default_factory=tuple)
    attention_items: tuple[DashboardAttentionItemDTO, ...] = field(default_factory=tuple)
    ar_aging: DashboardAgingSnapshotDTO = field(default_factory=DashboardAgingSnapshotDTO)
    ap_aging: DashboardAgingSnapshotDTO = field(default_factory=DashboardAgingSnapshotDTO)
    cash_liquidity: DashboardCashLiquidityDTO = field(default_factory=DashboardCashLiquidityDTO)
    as_of_date: date | None = None
    loaded_at: datetime | None = None
    period_label: str = ""
