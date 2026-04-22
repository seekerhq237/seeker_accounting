from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.fixed_assets.dto.asset_usage_record_commands import CreateAssetUsageRecordCommand
from seeker_accounting.modules.fixed_assets.dto.asset_usage_record_dto import AssetUsageRecordDTO
from seeker_accounting.modules.fixed_assets.models.asset_usage_record import AssetUsageRecord
from seeker_accounting.modules.fixed_assets.repositories.asset_repository import AssetRepository
from seeker_accounting.modules.fixed_assets.repositories.asset_usage_record_repository import (
    AssetUsageRecordRepository,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

AssetUsageRecordRepositoryFactory = Callable[[Session], AssetUsageRecordRepository]
AssetRepositoryFactory = Callable[[Session], AssetRepository]

_USAGE_METHODS = frozenset({"units_of_production", "depletion"})


class AssetUsageService:
    """CRUD for per-period usage records for units-of-production and depletion assets."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        usage_record_repository_factory: AssetUsageRecordRepositoryFactory,
        asset_repository_factory: AssetRepositoryFactory,
        audit_service: "AuditService | None" = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._usage_record_repository_factory = usage_record_repository_factory
        self._asset_repository_factory = asset_repository_factory
        self._audit_service = audit_service

    def list_usage_records(self, company_id: int, asset_id: int) -> list[AssetUsageRecordDTO]:
        with self._unit_of_work_factory() as uow:
            repo = self._usage_record_repository_factory(uow.session)
            rows = repo.list_by_asset(company_id, asset_id)
            return [self._to_dto(r) for r in rows]

    def create_usage_record(
        self, company_id: int, asset_id: int, command: CreateAssetUsageRecordCommand
    ) -> AssetUsageRecordDTO:
        with self._unit_of_work_factory() as uow:
            asset_repo = self._asset_repository_factory(uow.session)
            asset = asset_repo.get_by_id(company_id, asset_id)
            if asset is None:
                raise NotFoundError(f"Asset {asset_id} not found.")
            if asset.depreciation_method_code not in _USAGE_METHODS:
                raise ValidationError(
                    f"Usage records can only be added to assets using "
                    f"units_of_production or depletion method. "
                    f"This asset uses '{asset.depreciation_method_code}'."
                )
            if Decimal(str(command.units_used)) <= Decimal("0"):
                raise ValidationError("Units used must be greater than zero.")

            repo = self._usage_record_repository_factory(uow.session)
            row = AssetUsageRecord(
                company_id=company_id,
                asset_id=asset_id,
                usage_date=command.usage_date,
                units_used=command.units_used,
                notes=command.notes,
                created_at=datetime.utcnow(),
            )
            repo.save(row)
            uow.commit()
            from seeker_accounting.modules.audit.event_type_catalog import ASSET_USAGE_RECORD_CREATED
            self._record_audit(company_id, ASSET_USAGE_RECORD_CREATED, "AssetUsageRecord", row.id, f"Created usage record for asset id={asset_id}")
            return self._to_dto(row)

    def delete_usage_record(self, company_id: int, record_id: int) -> None:
        with self._unit_of_work_factory() as uow:
            repo = self._usage_record_repository_factory(uow.session)
            row = repo.get_by_id(company_id, record_id)
            if row is None:
                raise NotFoundError(f"Usage record {record_id} not found.")
            uow.session.delete(row)
            uow.commit()
            from seeker_accounting.modules.audit.event_type_catalog import ASSET_USAGE_RECORD_DELETED
            self._record_audit(company_id, ASSET_USAGE_RECORD_DELETED, "AssetUsageRecord", record_id, f"Deleted usage record id={record_id}")

    def _to_dto(self, row: AssetUsageRecord) -> AssetUsageRecordDTO:
        return AssetUsageRecordDTO(
            id=row.id,
            company_id=row.company_id,
            asset_id=row.asset_id,
            usage_date=row.usage_date,
            units_used=row.units_used,
            notes=row.notes,
            created_at=row.created_at,
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
