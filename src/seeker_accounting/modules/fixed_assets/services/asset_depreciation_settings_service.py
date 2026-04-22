from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.fixed_assets.dto.asset_depreciation_settings_commands import (
    UpsertAssetDepreciationSettingsCommand,
)
from seeker_accounting.modules.fixed_assets.dto.asset_depreciation_settings_dto import AssetDepreciationSettingsDTO
from seeker_accounting.modules.fixed_assets.models.asset_depreciation_settings import AssetDepreciationSettings
from seeker_accounting.modules.fixed_assets.repositories.asset_depreciation_settings_repository import (
    AssetDepreciationSettingsRepository,
)
from seeker_accounting.modules.fixed_assets.repositories.asset_repository import AssetRepository
from seeker_accounting.modules.fixed_assets.repositories.macrs_profile_repository import MacrsProfileRepository
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

AssetDepreciationSettingsRepositoryFactory = Callable[[Session], AssetDepreciationSettingsRepository]
AssetRepositoryFactory = Callable[[Session], AssetRepository]
MacrsProfileRepositoryFactory = Callable[[Session], MacrsProfileRepository]

_VALID_CONVENTION_CODES = frozenset({"half_year", "mid_quarter_q1", "mid_month"})


class AssetDepreciationSettingsService:
    """Create or update method-specific depreciation parameters for an asset.

    One settings row per asset (upsert semantics via save).
    """

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        settings_repository_factory: AssetDepreciationSettingsRepositoryFactory,
        asset_repository_factory: AssetRepositoryFactory,
        macrs_profile_repository_factory: MacrsProfileRepositoryFactory,
        audit_service: "AuditService | None" = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._settings_repository_factory = settings_repository_factory
        self._asset_repository_factory = asset_repository_factory
        self._macrs_profile_repository_factory = macrs_profile_repository_factory
        self._audit_service = audit_service

    def get_settings(self, company_id: int, asset_id: int) -> AssetDepreciationSettingsDTO | None:
        with self._unit_of_work_factory() as uow:
            repo = self._settings_repository_factory(uow.session)
            row = repo.get_by_asset(company_id, asset_id)
            return self._to_dto(row) if row else None

    def upsert_settings(
        self, company_id: int, asset_id: int, command: UpsertAssetDepreciationSettingsCommand
    ) -> AssetDepreciationSettingsDTO:
        with self._unit_of_work_factory() as uow:
            asset_repo = self._asset_repository_factory(uow.session)
            asset = asset_repo.get_by_id(company_id, asset_id)
            if asset is None:
                raise NotFoundError(f"Asset {asset_id} not found.")

            self._validate(command, uow.session)

            settings_repo = self._settings_repository_factory(uow.session)
            existing = settings_repo.get_by_asset(company_id, asset_id)
            now = datetime.utcnow()

            if existing is None:
                existing = AssetDepreciationSettings(
                    company_id=company_id,
                    asset_id=asset_id,
                    created_at=now,
                    updated_at=now,
                )

            existing.declining_factor = command.declining_factor
            existing.switch_to_straight_line = command.switch_to_straight_line
            existing.expected_total_units = command.expected_total_units
            existing.interest_rate = command.interest_rate
            existing.macrs_profile_id = command.macrs_profile_id
            existing.macrs_convention_code = command.macrs_convention_code
            existing.updated_at = now

            settings_repo.save(existing)
            uow.commit()
            from seeker_accounting.modules.audit.event_type_catalog import ASSET_DEPRECIATION_SETTINGS_UPSERTED
            self._record_audit(company_id, ASSET_DEPRECIATION_SETTINGS_UPSERTED, "AssetDepreciationSettings", existing.id, f"Upserted depreciation settings for asset id={asset_id}")
            return self._to_dto(existing)

    def delete_settings(self, company_id: int, asset_id: int) -> None:
        with self._unit_of_work_factory() as uow:
            settings_repo = self._settings_repository_factory(uow.session)
            row = settings_repo.get_by_asset(company_id, asset_id)
            if row is not None:
                settings_repo.delete(row)
                uow.commit()
                from seeker_accounting.modules.audit.event_type_catalog import ASSET_DEPRECIATION_SETTINGS_DELETED
                self._record_audit(company_id, ASSET_DEPRECIATION_SETTINGS_DELETED, "AssetDepreciationSettings", row.id, f"Deleted depreciation settings for asset id={asset_id}")

    # ------------------------------------------------------------------

    def _validate(self, cmd: UpsertAssetDepreciationSettingsCommand, session: Session) -> None:
        if cmd.declining_factor is not None:
            factor = Decimal(str(cmd.declining_factor))
            if factor <= Decimal("0") or factor > Decimal("4"):
                raise ValidationError("Declining factor must be between 0 (exclusive) and 4.")
        if cmd.expected_total_units is not None:
            if Decimal(str(cmd.expected_total_units)) <= Decimal("0"):
                raise ValidationError("Expected total units must be greater than zero.")
        if cmd.interest_rate is not None:
            rate = Decimal(str(cmd.interest_rate))
            if rate <= Decimal("0") or rate >= Decimal("1"):
                raise ValidationError("Interest rate must be between 0 and 1 (exclusive), e.g. 0.005 for 0.5%.")
        if cmd.macrs_profile_id is not None:
            macrs_repo = self._macrs_profile_repository_factory(session)
            if macrs_repo.get_by_id(cmd.macrs_profile_id) is None:
                raise ValidationError(f"MACRS profile {cmd.macrs_profile_id} not found.")
        if cmd.macrs_convention_code is not None:
            if cmd.macrs_convention_code not in _VALID_CONVENTION_CODES:
                raise ValidationError(
                    f"MACRS convention code '{cmd.macrs_convention_code}' is not valid. "
                    f"Valid: {', '.join(sorted(_VALID_CONVENTION_CODES))}."
                )

    def _to_dto(self, row: AssetDepreciationSettings) -> AssetDepreciationSettingsDTO:
        return AssetDepreciationSettingsDTO(
            id=row.id,
            company_id=row.company_id,
            asset_id=row.asset_id,
            declining_factor=row.declining_factor,
            switch_to_straight_line=row.switch_to_straight_line,
            expected_total_units=row.expected_total_units,
            interest_rate=row.interest_rate,
            macrs_profile_id=row.macrs_profile_id,
            macrs_convention_code=row.macrs_convention_code,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _record_audit(
        self,
        company_id: int,
        event_type_code: str,
        entity_type: str,
        entity_id: int | None,
        description: str,
    ) -> None:
        if self._audit_service is None:
            return
        from seeker_accounting.modules.audit.dto.audit_event_dto import RecordAuditEventCommand
        from seeker_accounting.modules.audit.event_type_catalog import MODULE_FIXED_ASSETS
        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type_code,
                    module_code=MODULE_FIXED_ASSETS,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    description=description,
                ),
            )
        except Exception:
            pass  # Audit must not break business operations
