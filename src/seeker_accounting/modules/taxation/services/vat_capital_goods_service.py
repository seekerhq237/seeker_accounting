"""VAT Capital-Goods Service (T38).

Implements the multi-year capital-goods VAT adjustment scheme.
Under Cameroon DGI rules (aligned with OHADA), a company that
recovers VAT on a capital asset must monitor that recovery over the
statutory period (default 5 years).  Each year, if the pro-rata
percentage changes the company must make an upward or downward
adjustment proportional to one fifth (or one nth) of the initial
VAT amount.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.taxation.dto.capital_goods_dto import (
    CapitalGoodAdjustmentDTO,
    CapitalGoodDTO,
    RegisterCapitalGoodCommand,
)
from seeker_accounting.modules.taxation.models.vat_capital_good import VatCapitalGood
from seeker_accounting.modules.taxation.repositories.company_tax_profile_repository import (
    CompanyTaxProfileRepository,
)
from seeker_accounting.modules.taxation.repositories.vat_capital_good_repository import (
    VatCapitalGoodRepository,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

CapitalGoodRepoFactory = Callable[[Session], VatCapitalGoodRepository]
TaxProfileRepoFactory = Callable[[Session], CompanyTaxProfileRepository]


class VatCapitalGoodsService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        capital_good_repo_factory: CapitalGoodRepoFactory,
        tax_profile_repo_factory: TaxProfileRepoFactory,
    ) -> None:
        self._uow_factory = uow_factory
        self._repo_factory = capital_good_repo_factory
        self._profile_repo_factory = tax_profile_repo_factory

    # ── Registration ─────────────────────────────────────────────────

    def register(
        self, company_id: int, command: RegisterCapitalGoodCommand
    ) -> CapitalGoodDTO:
        """Register a new capital asset in the VAT capital-goods scheme."""
        self._validate_command(command)
        with self._uow_factory() as uow:
            repo = self._repo_factory(uow.session)
            asset = VatCapitalGood(
                company_id=company_id,
                fixed_asset_id=command.fixed_asset_id,
                asset_description=command.asset_description.strip(),
                acquisition_date=command.acquisition_date,
                base_amount=command.base_amount,
                vat_recovered_initial=command.vat_recovered_initial,
                monitored_years=command.monitored_years,
                status_code="ACTIVE",
                notes=command.notes,
            )
            repo.add(asset)
            uow.session.flush()
            return self._to_dto(asset)

    def dispose(
        self,
        company_id: int,
        asset_id: int,
        disposal_date: date,
    ) -> CapitalGoodDTO:
        """Mark an asset as disposed, stopping future monitoring."""
        with self._uow_factory() as uow:
            repo = self._repo_factory(uow.session)
            asset = repo.get(asset_id, company_id)
            if asset is None:
                raise NotFoundError(
                    f"Capital good {asset_id} not found for this company."
                )
            if asset.status_code == "DISPOSED":
                raise ValidationError("Asset is already disposed.")
            if disposal_date < asset.acquisition_date:
                raise ValidationError(
                    "Disposal date cannot be before acquisition date."
                )
            asset.status_code = "DISPOSED"
            asset.disposal_date = disposal_date
            return self._to_dto(asset)

    def list_active(self, company_id: int) -> list[CapitalGoodDTO]:
        with self._uow_factory() as uow:
            repo = self._repo_factory(uow.session)
            assets = repo.list_active(company_id)
            return [self._to_dto(a) for a in assets]

    def list_all(self, company_id: int) -> list[CapitalGoodDTO]:
        with self._uow_factory() as uow:
            repo = self._repo_factory(uow.session)
            assets = repo.list_all(company_id)
            return [self._to_dto(a) for a in assets]

    def get(self, company_id: int, asset_id: int) -> CapitalGoodDTO:
        with self._uow_factory() as uow:
            repo = self._repo_factory(uow.session)
            asset = repo.get(asset_id, company_id)
            if asset is None:
                raise NotFoundError(
                    f"Capital good {asset_id} not found for this company."
                )
            return self._to_dto(asset)

    # ── Annual adjustment computation ────────────────────────────────

    def compute_annual_adjustments(
        self,
        company_id: int,
        calendar_year: int,
        current_pro_rata_pct: float | None = None,
    ) -> list[CapitalGoodAdjustmentDTO]:
        """
        Compute required VAT adjustments for ``calendar_year`` for all active
        capital goods still within their monitoring window.
        """
        with self._uow_factory() as uow:
            repo = self._repo_factory(uow.session)
            assets = repo.list_active(company_id)
            if not assets:
                return []

            if current_pro_rata_pct is None:
                profile_repo = self._profile_repo_factory(uow.session)
                profile = profile_repo.get_by_company(company_id)
                if profile is None:
                    current_pro_rata_pct = 100.0
                else:
                    raw = getattr(profile, "vat_pro_rata_percent", None)
                    current_pro_rata_pct = float(raw) if raw is not None else 100.0

            results: list[CapitalGoodAdjustmentDTO] = []
            for asset in assets:
                dto = self._compute_asset_adjustment(
                    asset, calendar_year, current_pro_rata_pct
                )
                if dto is not None:
                    results.append(dto)
            return results

    def _compute_asset_adjustment(
        self,
        asset: VatCapitalGood,
        calendar_year: int,
        current_pro_rata_pct: float,
    ) -> CapitalGoodAdjustmentDTO | None:
        """Return adjustment DTO if the asset is in its monitoring window, else None."""
        acquisition_year = asset.acquisition_date.year
        year_number = calendar_year - acquisition_year
        # year_number: 0 = acquisition year, 1..n-1 = subsequent years
        if year_number <= 0 or year_number >= asset.monitored_years:
            return None

        # Annual slice of initial VAT
        annual_vat = (
            asset.vat_recovered_initial / Decimal(str(asset.monitored_years))
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Initial pro-rata: assume 100% unless pro-rata was set at time of entry.
        # We use vat_recovered_initial / (base_amount * std_rate) to back-calculate,
        # but that requires knowing the rate.  Instead, store initial % as 100% for
        # fully taxable companies.  The real back-calculation is done outside.
        # For now we assume 100% initial pro-rata (full recovery assumed at acquisition).
        initial_pro_rata = 100.0

        # Adjustment = annual_vat × (current% - initial%) / 100
        # Positive = clawback (recovery was too high)
        # Negative = further deduction (recovery was too low)
        adjustment = (
            annual_vat * Decimal(str((current_pro_rata_pct - initial_pro_rata) / 100))
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        return CapitalGoodAdjustmentDTO(
            capital_good_id=asset.id,
            asset_description=asset.asset_description,
            acquisition_date=asset.acquisition_date,
            year_number=year_number,
            calendar_year=calendar_year,
            pro_rata_used=current_pro_rata_pct,
            initial_pro_rata=initial_pro_rata,
            adjustment_amount=adjustment,
            base_annual_vat=annual_vat,
        )

    # ── Validation ───────────────────────────────────────────────────

    @staticmethod
    def _validate_command(cmd: RegisterCapitalGoodCommand) -> None:
        errors: list[str] = []
        if not cmd.asset_description or not cmd.asset_description.strip():
            errors.append("Asset description is required.")
        if cmd.base_amount <= Decimal("0"):
            errors.append("Base amount must be positive.")
        if cmd.vat_recovered_initial < Decimal("0"):
            errors.append("VAT recovered cannot be negative.")
        if cmd.monitored_years < 1:
            errors.append("Monitored years must be at least 1.")
        if errors:
            raise ValidationError("; ".join(errors))

    # ── Mapping ──────────────────────────────────────────────────────

    @staticmethod
    def _to_dto(asset: VatCapitalGood) -> CapitalGoodDTO:
        return CapitalGoodDTO(
            id=asset.id,
            company_id=asset.company_id,
            fixed_asset_id=asset.fixed_asset_id,
            asset_description=asset.asset_description,
            acquisition_date=asset.acquisition_date,
            base_amount=asset.base_amount,
            vat_recovered_initial=asset.vat_recovered_initial,
            monitored_years=asset.monitored_years,
            status_code=asset.status_code,
            disposal_date=asset.disposal_date,
            notes=asset.notes,
        )
