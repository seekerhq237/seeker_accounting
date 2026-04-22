from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.fixed_assets.dto.asset_component_commands import (
    CreateAssetComponentCommand,
    UpdateAssetComponentCommand,
)
from seeker_accounting.modules.fixed_assets.dto.asset_component_dto import AssetComponentDTO
from seeker_accounting.modules.fixed_assets.models.asset_component import AssetComponent
from seeker_accounting.modules.fixed_assets.repositories.asset_component_repository import AssetComponentRepository
from seeker_accounting.modules.fixed_assets.repositories.asset_repository import AssetRepository
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

AssetComponentRepositoryFactory = Callable[[Session], AssetComponentRepository]
AssetRepositoryFactory = Callable[[Session], AssetRepository]

# All method codes valid for components (not 'component' itself — no recursion)
_COMPONENT_VALID_METHODS = frozenset({
    "straight_line", "declining_balance", "double_declining_balance",
    "declining_balance_150", "reducing_balance", "sum_of_years_digits",
    "units_of_production", "annuity", "sinking_fund", "macrs", "amortization",
})


class AssetComponentService:
    """CRUD for child components of assets using the 'component' depreciation method."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        component_repository_factory: AssetComponentRepositoryFactory,
        asset_repository_factory: AssetRepositoryFactory,
        audit_service: "AuditService | None" = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._component_repository_factory = component_repository_factory
        self._asset_repository_factory = asset_repository_factory
        self._audit_service = audit_service

    def list_components(self, company_id: int, asset_id: int) -> list[AssetComponentDTO]:
        with self._unit_of_work_factory() as uow:
            repo = self._component_repository_factory(uow.session)
            rows = repo.list_by_asset(company_id, asset_id, active_only=False)
            return [self._to_dto(r) for r in rows]

    def create_component(
        self, company_id: int, asset_id: int, command: CreateAssetComponentCommand
    ) -> AssetComponentDTO:
        with self._unit_of_work_factory() as uow:
            asset_repo = self._asset_repository_factory(uow.session)
            asset = asset_repo.get_by_id(company_id, asset_id)
            if asset is None:
                raise NotFoundError(f"Asset {asset_id} not found.")
            if asset.depreciation_method_code != "component":
                raise ValidationError(
                    "Components can only be added to assets using the 'component' depreciation method."
                )
            self._validate(command.component_name, command.acquisition_cost,
                           command.salvage_value, command.useful_life_months,
                           command.depreciation_method_code)
            now = datetime.utcnow()
            row = AssetComponent(
                company_id=company_id,
                parent_asset_id=asset_id,
                component_name=command.component_name.strip(),
                acquisition_cost=command.acquisition_cost,
                salvage_value=command.salvage_value,
                useful_life_months=command.useful_life_months,
                depreciation_method_code=command.depreciation_method_code,
                notes=command.notes,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            repo = self._component_repository_factory(uow.session)
            repo.save(row)
            uow.commit()
            from seeker_accounting.modules.audit.event_type_catalog import ASSET_COMPONENT_CREATED
            self._record_audit(company_id, ASSET_COMPONENT_CREATED, "AssetComponent", row.id, f"Created asset component for asset id={asset_id}")
            return self._to_dto(row)

    def update_component(
        self, company_id: int, component_id: int, command: UpdateAssetComponentCommand
    ) -> AssetComponentDTO:
        with self._unit_of_work_factory() as uow:
            repo = self._component_repository_factory(uow.session)
            row = repo.get_by_id(company_id, component_id)
            if row is None:
                raise NotFoundError(f"Asset component {component_id} not found.")
            self._validate(command.component_name, command.acquisition_cost,
                           command.salvage_value, command.useful_life_months,
                           command.depreciation_method_code)
            row.component_name = command.component_name.strip()
            row.acquisition_cost = command.acquisition_cost
            row.salvage_value = command.salvage_value
            row.useful_life_months = command.useful_life_months
            row.depreciation_method_code = command.depreciation_method_code
            row.notes = command.notes
            row.is_active = command.is_active
            row.updated_at = datetime.utcnow()
            repo.save(row)
            uow.commit()
            from seeker_accounting.modules.audit.event_type_catalog import ASSET_COMPONENT_UPDATED
            self._record_audit(company_id, ASSET_COMPONENT_UPDATED, "AssetComponent", row.id, f"Updated asset component id={component_id}")
            return self._to_dto(row)

    # ------------------------------------------------------------------

    def _validate(
        self, name: str, cost: Decimal, salvage: Decimal | None,
        life: int, method: str
    ) -> None:
        if not name or not name.strip():
            raise ValidationError("Component name is required.")
        if Decimal(str(cost)) <= Decimal("0"):
            raise ValidationError("Acquisition cost must be greater than zero.")
        if salvage is not None and Decimal(str(salvage)) < Decimal("0"):
            raise ValidationError("Salvage value cannot be negative.")
        if salvage is not None and Decimal(str(salvage)) >= Decimal(str(cost)):
            raise ValidationError("Salvage value must be less than acquisition cost.")
        if life <= 0:
            raise ValidationError("Useful life months must be greater than zero.")
        if method not in _COMPONENT_VALID_METHODS:
            raise ValidationError(
                f"Depreciation method '{method}' is not valid for components. "
                f"Valid: {', '.join(sorted(_COMPONENT_VALID_METHODS))}."
            )

    def _to_dto(self, row: AssetComponent) -> AssetComponentDTO:
        return AssetComponentDTO(
            id=row.id,
            company_id=row.company_id,
            parent_asset_id=row.parent_asset_id,
            component_name=row.component_name,
            acquisition_cost=row.acquisition_cost,
            salvage_value=row.salvage_value,
            useful_life_months=row.useful_life_months,
            depreciation_method_code=row.depreciation_method_code,
            notes=row.notes,
            is_active=row.is_active,
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
