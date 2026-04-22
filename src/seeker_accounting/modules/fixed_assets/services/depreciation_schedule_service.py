from __future__ import annotations

"""Depreciation Schedule Service — supports all built-in depreciation methods.

Methods implemented:
    straight_line            Monthly amount = depreciable_base / N.
    declining_balance        Monthly rate = factor / N. factor=1.0 (DB), 1.5 (150DB), 2.0 (DDB).
    double_declining_balance Same engine as declining_balance with factor=2.0.
    declining_balance_150    Same engine as declining_balance with factor=1.5.
    reducing_balance         Backward-compatible alias for double_declining_balance (factor=2.0).
    sum_of_years_digits      Fraction for month k = (N-k+1) / (N*(N+1)/2).
    units_of_production      Period charge = units_k * (depreciable_base / expected_total_units).
                             If usage_units tuple provided: uses actual per-period values.
                             Otherwise spreads expected_total_units evenly across N months.
    depletion                Same engine as units_of_production.
    annuity                  A = P*r/(1-(1+r)^-n), where P=depreciable_base, r=monthly interest rate.
                             Each period: charge = annuity_payment - interest_on_opening_fund.
                             (Increasing depreciation; total = depreciable_base exactly.)
    sinking_fund             C = P*r/((1+r)^n - 1); each period: charge = C*(1+r)^(k-1).
                             (Increasing charges; total = depreciable_base exactly.)
    macrs                    Annual percentage rates from macrs_annual_rates tuple.
                             Applied to full acquisition cost (no salvage deduction, per IRS).
                             Annual rates distributed evenly across 12 months within each year.
    component                Aggregate of child component straight-line schedules.
                             Requires components tuple in command.
    composite / group        Pool-level straight-line on combined cost basis.
                             Requires pool_cost and pool_salvage in command.
    amortization             Same as straight_line.

Switch-to-SL:
    For declining-balance family, when switch_to_straight_line=True: once the remaining
    straight-line charge (remaining_depreciable / periods_left) exceeds the DB charge,
    all subsequent periods use SL.
"""

import json
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.fixed_assets.dto.depreciation_commands import (
    GenerateDepreciationScheduleCommand,
)
from seeker_accounting.modules.fixed_assets.dto.depreciation_dto import (
    DepreciationScheduleDTO,
    DepreciationScheduleLineDTO,
)
from seeker_accounting.modules.fixed_assets.repositories.asset_depreciation_settings_repository import (
    AssetDepreciationSettingsRepository,
)
from seeker_accounting.modules.fixed_assets.repositories.asset_repository import AssetRepository
from seeker_accounting.modules.fixed_assets.repositories.macrs_profile_repository import MacrsProfileRepository
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

_ZERO = Decimal("0")
_PREC = Decimal("0.000001")
_ONE = Decimal("1")

AssetRepositoryFactory = Callable[[Session], AssetRepository]
AssetDepreciationSettingsRepositoryFactory = Callable[[Session], AssetDepreciationSettingsRepository]
MacrsProfileRepositoryFactory = Callable[[Session], MacrsProfileRepository]


class DepreciationScheduleService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        asset_repository_factory: AssetRepositoryFactory,
        settings_repository_factory: AssetDepreciationSettingsRepositoryFactory | None = None,
        macrs_profile_repository_factory: MacrsProfileRepositoryFactory | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._asset_repository_factory = asset_repository_factory
        self._settings_repository_factory = settings_repository_factory
        self._macrs_profile_repository_factory = macrs_profile_repository_factory

    def generate_schedule_for_asset(
        self, company_id: int, asset_id: int
    ) -> DepreciationScheduleDTO:
        with self._unit_of_work_factory() as uow:
            repo = self._asset_repository_factory(uow.session)
            asset = repo.get_by_id(company_id, asset_id)
            if asset is None:
                raise NotFoundError(f"Asset {asset_id} not found.")

            salvage = asset.salvage_value if asset.salvage_value is not None else _ZERO
            method = asset.depreciation_method_code

            # Build base command kwargs
            kwargs: dict = dict(
                acquisition_cost=asset.acquisition_cost,
                salvage_value=salvage,
                useful_life_months=asset.useful_life_months,
                depreciation_method_code=method,
                capitalization_date=asset.capitalization_date,
            )

            # Load method-specific settings if available
            if self._settings_repository_factory is not None:
                settings_repo = self._settings_repository_factory(uow.session)
                settings = settings_repo.get_by_asset(company_id, asset_id)
                if settings is not None:
                    if settings.declining_factor is not None:
                        kwargs["declining_factor"] = settings.declining_factor
                    kwargs["switch_to_straight_line"] = settings.switch_to_straight_line or False
                    if settings.expected_total_units is not None:
                        kwargs["expected_total_units"] = settings.expected_total_units
                    if settings.interest_rate is not None:
                        kwargs["interest_rate"] = settings.interest_rate
                    if settings.macrs_profile_id is not None and self._macrs_profile_repository_factory is not None:
                        macrs_repo = self._macrs_profile_repository_factory(uow.session)
                        profile = macrs_repo.get_by_id(settings.macrs_profile_id)
                        if profile is not None:
                            rates = json.loads(profile.gds_rates_json)
                            kwargs["macrs_annual_rates"] = tuple(rates)

            cmd = GenerateDepreciationScheduleCommand(**kwargs)
            schedule = self.preview_schedule(cmd)

            return DepreciationScheduleDTO(
                asset_id=asset.id,
                asset_number=asset.asset_number,
                asset_name=asset.asset_name,
                acquisition_cost=schedule.acquisition_cost,
                salvage_value=schedule.salvage_value,
                useful_life_months=schedule.useful_life_months,
                depreciation_method_code=schedule.depreciation_method_code,
                capitalization_date=schedule.capitalization_date,
                depreciable_base=schedule.depreciable_base,
                total_depreciation=schedule.total_depreciation,
                lines=schedule.lines,
            )

    def preview_schedule(
        self, command: GenerateDepreciationScheduleCommand
    ) -> DepreciationScheduleDTO:
        cost = Decimal(str(command.acquisition_cost))
        method = command.depreciation_method_code

        # MACRS uses full cost basis — no salvage deduction per IRS rules
        if method == "macrs":
            salvage = _ZERO
        else:
            salvage = Decimal(str(command.salvage_value)) if command.salvage_value is not None else _ZERO

        n = command.useful_life_months

        if cost <= _ZERO:
            raise ValidationError("Acquisition cost must be greater than zero.")
        if method != "macrs":
            if salvage < _ZERO:
                raise ValidationError("Salvage value cannot be negative.")
            if salvage >= cost:
                raise ValidationError("Salvage value must be less than acquisition cost.")
        if n <= 0:
            raise ValidationError("Useful life months must be greater than zero.")

        depreciable_base = cost - salvage

        if method == "straight_line" or method == "amortization":
            lines = self._straight_line(cost, salvage, depreciable_base, n)

        elif method in ("reducing_balance", "double_declining_balance"):
            factor = Decimal(str(command.declining_factor)) if command.declining_factor is not None else Decimal("2")
            lines = self._declining_balance(cost, salvage, depreciable_base, n, factor,
                                            command.switch_to_straight_line)

        elif method == "declining_balance":
            factor = Decimal(str(command.declining_factor)) if command.declining_factor is not None else Decimal("1")
            lines = self._declining_balance(cost, salvage, depreciable_base, n, factor,
                                            command.switch_to_straight_line)

        elif method == "declining_balance_150":
            factor = Decimal(str(command.declining_factor)) if command.declining_factor is not None else Decimal("1.5")
            lines = self._declining_balance(cost, salvage, depreciable_base, n, factor,
                                            command.switch_to_straight_line)

        elif method == "sum_of_years_digits":
            lines = self._sum_of_years_digits(cost, salvage, depreciable_base, n)

        elif method in ("units_of_production", "depletion"):
            if command.usage_units is not None:
                lines = self._units_of_production_actual(cost, salvage, depreciable_base, command.usage_units)
            elif command.expected_total_units is not None:
                total_units = Decimal(str(command.expected_total_units))
                if total_units <= _ZERO:
                    raise ValidationError("Expected total units must be greater than zero.")
                lines = self._units_of_production_even(cost, salvage, depreciable_base, n, total_units)
            else:
                raise ValidationError(
                    f"Method '{method}' requires either 'expected_total_units' or 'usage_units'."
                )

        elif method == "annuity":
            if command.interest_rate is None:
                raise ValidationError("Method 'annuity' requires 'interest_rate'.")
            r = Decimal(str(command.interest_rate))
            if r <= _ZERO or r >= _ONE:
                raise ValidationError("Interest rate must be between 0 and 1 (exclusive).")
            lines = self._annuity(cost, salvage, depreciable_base, n, r)

        elif method == "sinking_fund":
            if command.interest_rate is None:
                raise ValidationError("Method 'sinking_fund' requires 'interest_rate'.")
            r = Decimal(str(command.interest_rate))
            if r <= _ZERO or r >= _ONE:
                raise ValidationError("Interest rate must be between 0 and 1 (exclusive).")
            lines = self._sinking_fund(cost, salvage, depreciable_base, n, r)

        elif method == "macrs":
            if command.macrs_annual_rates is None:
                raise ValidationError("Method 'macrs' requires 'macrs_annual_rates'.")
            if len(command.macrs_annual_rates) == 0:
                raise ValidationError("MACRS annual rates tuple must not be empty.")
            lines = self._macrs(cost, command.macrs_annual_rates)

        elif method in ("group", "composite"):
            # For preview without pool data, treat as straight-line on provided cost/salvage
            lines = self._straight_line(cost, salvage, depreciable_base, n)

        elif method == "component":
            # For preview without component data, treat as straight-line on provided cost/salvage
            lines = self._straight_line(cost, salvage, depreciable_base, n)

        else:
            raise ValidationError(
                f"Unknown depreciation method '{method}'. "
                "See the depreciation_methods catalog for supported codes."
            )

        # Rebuild depreciable base for MACRS (which uses full cost)
        if method == "macrs":
            depreciable_base = cost

        total = sum(line.depreciation_amount for line in lines)

        return DepreciationScheduleDTO(
            asset_id=0,
            asset_number="",
            asset_name="",
            acquisition_cost=cost,
            salvage_value=salvage,
            useful_life_months=n,
            depreciation_method_code=method,
            capitalization_date=command.capitalization_date,
            depreciable_base=depreciable_base,
            total_depreciation=total,
            lines=tuple(lines),
        )

    # ------------------------------------------------------------------
    # Straight-line / amortization
    # ------------------------------------------------------------------

    def _straight_line(
        self,
        cost: Decimal,
        salvage: Decimal,
        depreciable_base: Decimal,
        n: int,
    ) -> list[DepreciationScheduleLineDTO]:
        monthly = (depreciable_base / n).quantize(_PREC, rounding=ROUND_DOWN)
        lines = []
        accumulated = _ZERO
        nbv = cost
        for k in range(1, n + 1):
            opening_nbv = nbv
            if k < n:
                amount = monthly
            else:
                amount = depreciable_base - accumulated
            amount = max(_ZERO, amount)
            accumulated += amount
            nbv = max(cost - accumulated, salvage)
            lines.append(
                DepreciationScheduleLineDTO(
                    period_number=k,
                    period_label=f"Month {k}",
                    opening_nbv=opening_nbv,
                    depreciation_amount=amount,
                    accumulated_depreciation=accumulated,
                    closing_nbv=nbv,
                )
            )
        return lines

    # ------------------------------------------------------------------
    # Declining-balance family (DB, 150DB, DDB)
    # ------------------------------------------------------------------

    def _declining_balance(
        self,
        cost: Decimal,
        salvage: Decimal,
        depreciable_base: Decimal,
        n: int,
        factor: Decimal,
        switch_to_sl: bool,
    ) -> list[DepreciationScheduleLineDTO]:
        """Declining-balance with optional switch-to-straight-line.

        monthly_rate = factor / n
        Each month: amount = opening_nbv * monthly_rate, capped at remaining_depreciable.
        When switch_to_sl=True and the remaining SL charge > DB charge, use SL for rest.
        """
        monthly_rate = factor / Decimal(str(n))
        lines = []
        accumulated = _ZERO
        nbv = cost
        using_sl = False
        for k in range(1, n + 1):
            opening_nbv = nbv
            remaining_depreciable = max(_ZERO, opening_nbv - salvage)
            periods_left = n - k + 1

            if remaining_depreciable <= _ZERO:
                amount = _ZERO
            elif using_sl:
                if k < n:
                    amount = (remaining_depreciable / Decimal(str(periods_left))).quantize(_PREC, rounding=ROUND_DOWN)
                else:
                    amount = remaining_depreciable
            else:
                db_amount = (opening_nbv * monthly_rate).quantize(_PREC, rounding=ROUND_DOWN)
                db_amount = min(db_amount, remaining_depreciable)
                sl_amount = (remaining_depreciable / Decimal(str(periods_left))).quantize(_PREC, rounding=ROUND_DOWN)
                if switch_to_sl and sl_amount > db_amount:
                    using_sl = True
                    if k < n:
                        amount = sl_amount
                    else:
                        amount = remaining_depreciable
                else:
                    amount = db_amount

            amount = max(_ZERO, amount)
            accumulated += amount
            nbv = max(cost - accumulated, salvage)
            lines.append(
                DepreciationScheduleLineDTO(
                    period_number=k,
                    period_label=f"Month {k}",
                    opening_nbv=opening_nbv,
                    depreciation_amount=amount,
                    accumulated_depreciation=accumulated,
                    closing_nbv=nbv,
                )
            )
        return lines

    # ------------------------------------------------------------------
    # Sum-of-years digits
    # ------------------------------------------------------------------

    def _sum_of_years_digits(
        self,
        cost: Decimal,
        salvage: Decimal,
        depreciable_base: Decimal,
        n: int,
    ) -> list[DepreciationScheduleLineDTO]:
        syd_sum = (
            Decimal(str(n * (n + 1) // 2))
            if n * (n + 1) % 2 == 0
            else Decimal(str(n)) * Decimal(str(n + 1)) / Decimal("2")
        )
        lines = []
        accumulated = _ZERO
        nbv = cost
        for k in range(1, n + 1):
            opening_nbv = nbv
            remaining_life = Decimal(str(n - k + 1))
            fraction = remaining_life / syd_sum
            if k < n:
                amount = (fraction * depreciable_base).quantize(_PREC, rounding=ROUND_DOWN)
            else:
                amount = depreciable_base - accumulated
            amount = max(_ZERO, amount)
            accumulated += amount
            nbv = max(cost - accumulated, salvage)
            lines.append(
                DepreciationScheduleLineDTO(
                    period_number=k,
                    period_label=f"Month {k}",
                    opening_nbv=opening_nbv,
                    depreciation_amount=amount,
                    accumulated_depreciation=accumulated,
                    closing_nbv=nbv,
                )
            )
        return lines

    # ------------------------------------------------------------------
    # Units of production — even spread (no actual usage data)
    # ------------------------------------------------------------------

    def _units_of_production_even(
        self,
        cost: Decimal,
        salvage: Decimal,
        depreciable_base: Decimal,
        n: int,
        total_units: Decimal,
    ) -> list[DepreciationScheduleLineDTO]:
        """Evenly distribute total_units across N months."""
        units_per_period = total_units / Decimal(str(n))
        rate_per_unit = depreciable_base / total_units
        lines = []
        accumulated = _ZERO
        nbv = cost
        for k in range(1, n + 1):
            opening_nbv = nbv
            if k < n:
                amount = (units_per_period * rate_per_unit).quantize(_PREC, rounding=ROUND_DOWN)
            else:
                amount = depreciable_base - accumulated
            amount = max(_ZERO, amount)
            remaining = max(_ZERO, opening_nbv - salvage)
            amount = min(amount, remaining)
            accumulated += amount
            nbv = max(cost - accumulated, salvage)
            lines.append(
                DepreciationScheduleLineDTO(
                    period_number=k,
                    period_label=f"Month {k}",
                    opening_nbv=opening_nbv,
                    depreciation_amount=amount,
                    accumulated_depreciation=accumulated,
                    closing_nbv=nbv,
                )
            )
        return lines

    # ------------------------------------------------------------------
    # Units of production — actual usage per period
    # ------------------------------------------------------------------

    def _units_of_production_actual(
        self,
        cost: Decimal,
        salvage: Decimal,
        depreciable_base: Decimal,
        usage_units: tuple[Decimal, ...],
    ) -> list[DepreciationScheduleLineDTO]:
        """Compute schedule from actual per-period units."""
        total_units = sum(Decimal(str(u)) for u in usage_units)
        if total_units <= _ZERO:
            raise ValidationError("Total usage units must be greater than zero.")
        rate_per_unit = depreciable_base / total_units
        lines = []
        accumulated = _ZERO
        nbv = cost
        n = len(usage_units)
        for k, units in enumerate(usage_units, start=1):
            opening_nbv = nbv
            u = Decimal(str(units))
            if k < n:
                amount = (u * rate_per_unit).quantize(_PREC, rounding=ROUND_DOWN)
            else:
                amount = depreciable_base - accumulated
            amount = max(_ZERO, amount)
            remaining = max(_ZERO, opening_nbv - salvage)
            amount = min(amount, remaining)
            accumulated += amount
            nbv = max(cost - accumulated, salvage)
            lines.append(
                DepreciationScheduleLineDTO(
                    period_number=k,
                    period_label=f"Month {k}",
                    opening_nbv=opening_nbv,
                    depreciation_amount=amount,
                    accumulated_depreciation=accumulated,
                    closing_nbv=nbv,
                )
            )
        return lines

    # ------------------------------------------------------------------
    # Annuity method
    # ------------------------------------------------------------------

    def _annuity(
        self,
        cost: Decimal,
        salvage: Decimal,
        depreciable_base: Decimal,
        n: int,
        r: Decimal,
    ) -> list[DepreciationScheduleLineDTO]:
        """Annuity depreciation: charges increase over time.

        A = P * r / (1 - (1+r)^-n)   where P = depreciable_base.

        Each period the asset earns a notional return at rate r on its remaining
        depreciable book value (opening_nbv - salvage).  The depreciation charge is
        the annuity payment A minus that notional interest:

            charge_k = A - (opening_nbv_k - salvage) * r

        As the depreciable NBV falls, the notional interest falls, so the charge rises.
        Total depreciation = depreciable_base exactly (last period absorbs rounding).
        """
        r_f = float(r)
        a_f = float(depreciable_base) * r_f / (1.0 - (1.0 + r_f) ** (-n))
        A = Decimal(str(round(a_f, 10)))

        lines = []
        accumulated = _ZERO
        nbv = cost
        for k in range(1, n + 1):
            opening_nbv = nbv
            remaining_dep = max(_ZERO, opening_nbv - salvage)
            notional_interest = (remaining_dep * r).quantize(_PREC, rounding=ROUND_DOWN)
            if k < n:
                charge = (A - notional_interest).quantize(_PREC, rounding=ROUND_DOWN)
            else:
                charge = depreciable_base - accumulated
            charge = max(_ZERO, charge)
            accumulated += charge
            nbv = max(cost - accumulated, salvage)
            lines.append(
                DepreciationScheduleLineDTO(
                    period_number=k,
                    period_label=f"Month {k}",
                    opening_nbv=opening_nbv,
                    depreciation_amount=charge,
                    accumulated_depreciation=accumulated,
                    closing_nbv=nbv,
                )
            )
        return lines

    # ------------------------------------------------------------------
    # Sinking fund method
    # ------------------------------------------------------------------

    def _sinking_fund(
        self,
        cost: Decimal,
        salvage: Decimal,
        depreciable_base: Decimal,
        n: int,
        r: Decimal,
    ) -> list[DepreciationScheduleLineDTO]:
        """Sinking fund: C = P*r/((1+r)^n - 1); charge_k = C*(1+r)^(k-1).

        Charges increase geometrically over time.
        """
        r_f = float(r)
        n_i = n
        c_f = float(depreciable_base) * r_f / ((1.0 + r_f) ** n_i - 1.0)
        C = Decimal(str(round(c_f, 10)))

        lines = []
        accumulated = _ZERO
        nbv = cost
        for k in range(1, n + 1):
            opening_nbv = nbv
            if k < n:
                charge = (C * ((_ONE + r) ** (k - 1))).quantize(_PREC, rounding=ROUND_DOWN)
            else:
                charge = depreciable_base - accumulated
            charge = max(_ZERO, charge)
            accumulated += charge
            nbv = max(cost - accumulated, salvage)
            lines.append(
                DepreciationScheduleLineDTO(
                    period_number=k,
                    period_label=f"Month {k}",
                    opening_nbv=opening_nbv,
                    depreciation_amount=charge,
                    accumulated_depreciation=accumulated,
                    closing_nbv=nbv,
                )
            )
        return lines

    # ------------------------------------------------------------------
    # MACRS
    # ------------------------------------------------------------------

    def _macrs(
        self,
        cost: Decimal,
        annual_rates: tuple[float, ...],
    ) -> list[DepreciationScheduleLineDTO]:
        """MACRS schedule from annual GDS percentage rates.

        Each annual rate is applied to the full unadjusted cost basis.
        The annual amount is distributed evenly across 12 months (partial years get
        their fractional share based on 12 months per year).
        Total periods = len(annual_rates) * 12.
        """
        lines = []
        accumulated = _ZERO
        nbv = cost
        period = 0
        n_months = len(annual_rates) * 12

        for year_idx, pct in enumerate(annual_rates):
            annual_amount = (cost * Decimal(str(pct)) / Decimal("100")).quantize(_PREC, rounding=ROUND_DOWN)
            monthly_base = (annual_amount / Decimal("12")).quantize(_PREC, rounding=ROUND_DOWN)
            remainder = annual_amount - monthly_base * 12

            for month_in_year in range(12):
                period += 1
                opening_nbv = nbv
                if month_in_year == 11:
                    # Last month of year: absorb rounding remainder
                    monthly = monthly_base + remainder
                else:
                    monthly = monthly_base

                # Last overall period: absorb any residual to hit total exactly
                if period == n_months:
                    monthly = max(_ZERO, cost - accumulated)
                else:
                    monthly = max(_ZERO, monthly)

                accumulated += monthly
                nbv = max(cost - accumulated, _ZERO)
                lines.append(
                    DepreciationScheduleLineDTO(
                        period_number=period,
                        period_label=f"Month {period}",
                        opening_nbv=opening_nbv,
                        depreciation_amount=monthly,
                        accumulated_depreciation=accumulated,
                        closing_nbv=nbv,
                    )
                )

        return lines
