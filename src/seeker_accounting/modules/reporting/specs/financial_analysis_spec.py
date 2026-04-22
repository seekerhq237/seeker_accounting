from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_ZERO = Decimal("0.00")
_RATIO_QUANTIZE = Decimal("0.0001")
_AMOUNT_QUANTIZE = Decimal("0.01")
_PERCENT_QUANTIZE = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class MetricThresholdSpec:
    metric_code: str
    direction_code: str  # "higher_better" | "lower_better"
    warning_below: Decimal | None = None
    caution_below: Decimal | None = None
    caution_above: Decimal | None = None
    warning_above: Decimal | None = None


RATIO_THRESHOLDS: dict[str, MetricThresholdSpec] = {
    "current_ratio": MetricThresholdSpec(
        metric_code="current_ratio",
        direction_code="higher_better",
        warning_below=Decimal("1.00"),
        caution_below=Decimal("1.50"),
    ),
    "quick_ratio": MetricThresholdSpec(
        metric_code="quick_ratio",
        direction_code="higher_better",
        warning_below=Decimal("0.70"),
        caution_below=Decimal("1.00"),
    ),
    "cash_ratio": MetricThresholdSpec(
        metric_code="cash_ratio",
        direction_code="higher_better",
        warning_below=Decimal("0.10"),
        caution_below=Decimal("0.20"),
    ),
    "dso_days": MetricThresholdSpec(
        metric_code="dso_days",
        direction_code="lower_better",
        caution_above=Decimal("60"),
        warning_above=Decimal("90"),
    ),
    "dpo_days": MetricThresholdSpec(
        metric_code="dpo_days",
        direction_code="lower_better",
        caution_above=Decimal("90"),
        warning_above=Decimal("120"),
    ),
    "dio_days": MetricThresholdSpec(
        metric_code="dio_days",
        direction_code="lower_better",
        caution_above=Decimal("75"),
        warning_above=Decimal("120"),
    ),
    "cash_conversion_cycle": MetricThresholdSpec(
        metric_code="cash_conversion_cycle",
        direction_code="lower_better",
        caution_above=Decimal("45"),
        warning_above=Decimal("90"),
    ),
    "gross_margin": MetricThresholdSpec(
        metric_code="gross_margin",
        direction_code="higher_better",
        warning_below=Decimal("0.00"),
        caution_below=Decimal("0.15"),
    ),
    "operating_margin": MetricThresholdSpec(
        metric_code="operating_margin",
        direction_code="higher_better",
        warning_below=Decimal("0.00"),
        caution_below=Decimal("0.08"),
    ),
    "net_margin": MetricThresholdSpec(
        metric_code="net_margin",
        direction_code="higher_better",
        warning_below=Decimal("0.00"),
        caution_below=Decimal("0.05"),
    ),
    "return_on_assets": MetricThresholdSpec(
        metric_code="return_on_assets",
        direction_code="higher_better",
        warning_below=Decimal("0.00"),
        caution_below=Decimal("0.05"),
    ),
    "return_on_equity": MetricThresholdSpec(
        metric_code="return_on_equity",
        direction_code="higher_better",
        warning_below=Decimal("0.00"),
        caution_below=Decimal("0.10"),
    ),
    "debt_to_equity": MetricThresholdSpec(
        metric_code="debt_to_equity",
        direction_code="lower_better",
        caution_above=Decimal("1.50"),
        warning_above=Decimal("2.50"),
    ),
    "debt_ratio": MetricThresholdSpec(
        metric_code="debt_ratio",
        direction_code="lower_better",
        caution_above=Decimal("0.45"),
        warning_above=Decimal("0.65"),
    ),
    "equity_ratio": MetricThresholdSpec(
        metric_code="equity_ratio",
        direction_code="higher_better",
        warning_below=Decimal("0.20"),
        caution_below=Decimal("0.35"),
    ),
    "liabilities_to_assets": MetricThresholdSpec(
        metric_code="liabilities_to_assets",
        direction_code="lower_better",
        caution_above=Decimal("0.65"),
        warning_above=Decimal("0.80"),
    ),
}


FORMULA_LABELS: dict[str, str] = {
    "working_capital": "Current assets - current liabilities",
    "current_ratio": "Current assets / current liabilities",
    "quick_ratio": "(Current assets - inventories) / current liabilities",
    "cash_ratio": "Cash and cash equivalents / current liabilities",
    "dso_days": "(Average receivables / revenue) x days in period",
    "dpo_days": "(Average payables / posted purchase bills) x days in period",
    "dio_days": "(Average inventory / cost of sales) x days in period",
    "cash_conversion_cycle": "DSO + DIO - DPO",
    "receivables_turnover": "Revenue / average receivables",
    "payables_turnover": "Posted purchase bills / average payables",
    "inventory_turnover": "Cost of sales / average inventory",
    "gross_margin": "Gross profit / revenue",
    "operating_margin": "Operating profit / revenue",
    "net_margin": "Net profit / revenue",
    "return_on_assets": "Net profit / average total assets",
    "return_on_equity": "Net profit / average equity",
    "debt_to_equity": "Total liabilities / total equity",
    "debt_ratio": "Interest-bearing borrowings / total assets",
    "equity_ratio": "Total equity / total assets",
    "liabilities_to_assets": "Total liabilities / total assets",
}


MATERIAL_CHANGE_PERCENT = Decimal("10.00")
MATERIAL_WORKING_CAPITAL_CHANGE_PERCENT = Decimal("15.00")
MATERIAL_CYCLE_DAY_CHANGE = Decimal("10")
MATERIAL_MARGIN_CHANGE_PERCENTAGE_POINTS = Decimal("2.00")
MATERIAL_LEVERAGE_CHANGE = Decimal("0.20")


def to_amount(value: Decimal | None) -> Decimal:
    if value is None:
        return _ZERO
    return value.quantize(_AMOUNT_QUANTIZE, rounding=ROUND_HALF_UP)


def to_ratio(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return value.quantize(_RATIO_QUANTIZE, rounding=ROUND_HALF_UP)


def to_percent(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return (value * Decimal("100")).quantize(_PERCENT_QUANTIZE, rounding=ROUND_HALF_UP)


def safe_divide(
    numerator: Decimal | None,
    denominator: Decimal | None,
) -> Decimal | None:
    if numerator is None or denominator in {None, _ZERO}:
        return None
    try:
        return (numerator / denominator).quantize(_RATIO_QUANTIZE, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ZeroDivisionError):
        return None


def ratio_change(current_value: Decimal | None, prior_value: Decimal | None) -> Decimal | None:
    if current_value is None or prior_value is None:
        return None
    return (current_value - prior_value).quantize(_RATIO_QUANTIZE, rounding=ROUND_HALF_UP)


def percent_change(current_value: Decimal | None, prior_value: Decimal | None) -> Decimal | None:
    if current_value is None or prior_value in {None, _ZERO}:
        return None
    return (((current_value - prior_value) / prior_value) * Decimal("100")).quantize(
        _PERCENT_QUANTIZE,
        rounding=ROUND_HALF_UP,
    )


def average_balance(current_value: Decimal | None, prior_value: Decimal | None) -> Decimal | None:
    if current_value is None:
        return None
    if prior_value is None:
        return current_value.quantize(_AMOUNT_QUANTIZE, rounding=ROUND_HALF_UP)
    return ((current_value + prior_value) / Decimal("2")).quantize(
        _AMOUNT_QUANTIZE,
        rounding=ROUND_HALF_UP,
    )


def period_day_count(date_from: date | None, date_to: date | None) -> Decimal | None:
    if date_from is None or date_to is None:
        return None
    if date_to < date_from:
        return None
    return Decimal(str((date_to - date_from).days + 1))


def evaluate_status(metric_code: str, value: Decimal | None) -> tuple[str, str]:
    if value is None:
        return "unavailable", "Not available"

    threshold = RATIO_THRESHOLDS.get(metric_code)
    if threshold is None:
        return "neutral", "Observed"

    if threshold.direction_code == "higher_better":
        if threshold.warning_below is not None and value < threshold.warning_below:
            return "danger", "Under pressure"
        if threshold.caution_below is not None and value < threshold.caution_below:
            return "warning", "Watch closely"
        return "success", "Comfortable"

    if threshold.warning_above is not None and value > threshold.warning_above:
        return "danger", "Elevated"
    if threshold.caution_above is not None and value > threshold.caution_above:
        return "warning", "Rising"
    return "success", "Contained"


def format_ratio_value(metric_code: str, value: Decimal | None) -> str:
    if value is None:
        return "Not available"
    if metric_code in {"working_capital"}:
        return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,.2f}"
    if metric_code in {
        "gross_margin",
        "operating_margin",
        "net_margin",
        "return_on_assets",
        "return_on_equity",
        "equity_ratio",
        "debt_ratio",
        "liabilities_to_assets",
    }:
        percent = to_percent(value)
        return "Not available" if percent is None else f"{percent:,.2f}%"
    if metric_code in {"dso_days", "dpo_days", "dio_days", "cash_conversion_cycle"}:
        return f"{value.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP):,.1f} days"
    return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,.2f}x"
