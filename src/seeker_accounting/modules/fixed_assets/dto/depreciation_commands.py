from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class GenerateDepreciationScheduleCommand:
    """Command to preview a depreciation schedule with explicit settings (no DB required).

    Required fields apply to all methods.
    Optional fields are method-specific:

        declining_balance / double_declining_balance / declining_balance_150 / reducing_balance
            declining_factor         — multiplier applied to (1/N). Default: 2.0 for DDB, 1.0 for DB
            switch_to_straight_line  — switch to SL when SL charge exceeds DB charge

        units_of_production / depletion
            expected_total_units     — total estimated units over the asset's life
            usage_units              — tuple of actual units per period; if provided, overrides even distribution

        annuity / sinking_fund
            interest_rate            — periodic (monthly) interest rate, e.g. 0.005 for 0.5%

        macrs
            macrs_annual_rates       — tuple of annual percentage rates, e.g. (33.33, 44.45, 14.81, 7.41)
    """
    acquisition_cost: Decimal
    salvage_value: Decimal
    useful_life_months: int
    depreciation_method_code: str
    capitalization_date: date
    # DB family
    declining_factor: Decimal | None = field(default=None)
    switch_to_straight_line: bool = field(default=False)
    # Units of production / depletion
    expected_total_units: Decimal | None = field(default=None)
    usage_units: tuple[Decimal, ...] | None = field(default=None)
    # Annuity / sinking fund
    interest_rate: Decimal | None = field(default=None)
    # MACRS — annual percentage rates (len = recovery_years + 1 for half-year)
    macrs_annual_rates: tuple[float, ...] | None = field(default=None)


@dataclass(frozen=True, slots=True)
class CreateDepreciationRunCommand:
    run_date: date
    period_end_date: date


@dataclass(frozen=True, slots=True)
class PostDepreciationRunCommand:
    run_id: int
