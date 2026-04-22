from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.fixed_assets.dto.asset_depreciation_pool_commands import (
    AddPoolMemberCommand,
    CreateAssetDepreciationPoolCommand,
    UpdateAssetDepreciationPoolCommand,
)
from seeker_accounting.modules.fixed_assets.dto.asset_depreciation_pool_dto import (
    AssetDepreciationPoolDTO,
    AssetDepreciationPoolMemberDTO,
)
from seeker_accounting.modules.fixed_assets.models.asset_depreciation_pool import AssetDepreciationPool
from seeker_accounting.modules.fixed_assets.models.asset_depreciation_pool_member import AssetDepreciationPoolMember
from seeker_accounting.modules.fixed_assets.repositories.asset_depreciation_pool_repository import (
    AssetDepreciationPoolRepository,
)
from seeker_accounting.modules.fixed_assets.repositories.asset_repository import AssetRepository
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

AssetDepreciationPoolRepositoryFactory = Callable[[Session], AssetDepreciationPoolRepository]
AssetRepositoryFactory = Callable[[Session], AssetRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]

_VALID_POOL_TYPES = frozenset({"group", "composite"})
_POOL_VALID_METHODS = frozenset({"straight_line", "declining_balance", "double_declining_balance",
                                  "declining_balance_150", "reducing_balance", "sum_of_years_digits"})


class AssetDepreciationPoolService:
    """CRUD for group/composite depreciation pools."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        pool_repository_factory: AssetDepreciationPoolRepositoryFactory,
        asset_repository_factory: AssetRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        audit_service: "AuditService | None" = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._pool_repository_factory = pool_repository_factory
        self._asset_repository_factory = asset_repository_factory
        self._company_repository_factory = company_repository_factory
        self._audit_service = audit_service

    def list_pools(self, company_id: int, active_only: bool = False) -> list[AssetDepreciationPoolDTO]:
        with self._unit_of_work_factory() as uow:
            repo = self._pool_repository_factory(uow.session)
            rows = repo.list_by_company(company_id, active_only=active_only)
            return [self._to_dto(r) for r in rows]

    def get_pool(self, company_id: int, pool_id: int) -> AssetDepreciationPoolDTO:
        with self._unit_of_work_factory() as uow:
            repo = self._pool_repository_factory(uow.session)
            row = repo.get_by_id(company_id, pool_id)
            if row is None:
                raise NotFoundError(f"Depreciation pool {pool_id} not found.")
            return self._to_dto(row)

    def create_pool(
        self, company_id: int, command: CreateAssetDepreciationPoolCommand
    ) -> AssetDepreciationPoolDTO:
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            self._validate_pool(command.code, command.name, command.pool_type_code,
                                command.depreciation_method_code, command.useful_life_months)
            repo = self._pool_repository_factory(uow.session)
            if repo.get_by_code(company_id, command.code) is not None:
                raise ConflictError(f"Depreciation pool code '{command.code}' already exists.")
            now = datetime.utcnow()
            pool = AssetDepreciationPool(
                company_id=company_id,
                code=command.code.strip().upper(),
                name=command.name.strip(),
                pool_type_code=command.pool_type_code,
                depreciation_method_code=command.depreciation_method_code,
                useful_life_months=command.useful_life_months,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            repo.save(pool)
            uow.commit()
            from seeker_accounting.modules.audit.event_type_catalog import ASSET_DEPRECIATION_POOL_CREATED
            self._record_audit(company_id, ASSET_DEPRECIATION_POOL_CREATED, "AssetDepreciationPool", pool.id, f"Created depreciation pool '{command.code}'")
            return self._to_dto(pool)

    def update_pool(
        self, company_id: int, pool_id: int, command: UpdateAssetDepreciationPoolCommand
    ) -> AssetDepreciationPoolDTO:
        with self._unit_of_work_factory() as uow:
            repo = self._pool_repository_factory(uow.session)
            pool = repo.get_by_id(company_id, pool_id)
            if pool is None:
                raise NotFoundError(f"Depreciation pool {pool_id} not found.")
            if command.useful_life_months <= 0:
                raise ValidationError("Useful life months must be greater than zero.")
            pool.name = command.name.strip()
            pool.depreciation_method_code = command.depreciation_method_code
            pool.useful_life_months = command.useful_life_months
            pool.is_active = command.is_active
            pool.updated_at = datetime.utcnow()
            repo.save(pool)
            uow.commit()
            from seeker_accounting.modules.audit.event_type_catalog import ASSET_DEPRECIATION_POOL_UPDATED
            self._record_audit(company_id, ASSET_DEPRECIATION_POOL_UPDATED, "AssetDepreciationPool", pool.id, f"Updated depreciation pool id={pool_id}")
            return self._to_dto(pool)

    def add_member(
        self, company_id: int, pool_id: int, command: AddPoolMemberCommand
    ) -> AssetDepreciationPoolDTO:
        with self._unit_of_work_factory() as uow:
            pool_repo = self._pool_repository_factory(uow.session)
            pool = pool_repo.get_by_id(company_id, pool_id)
            if pool is None:
                raise NotFoundError(f"Depreciation pool {pool_id} not found.")
            asset_repo = self._asset_repository_factory(uow.session)
            asset = asset_repo.get_by_id(company_id, command.asset_id)
            if asset is None:
                raise NotFoundError(f"Asset {command.asset_id} not found.")
            # Check if already a member
            existing = pool_repo.get_active_member(command.asset_id)
            if existing is not None:
                raise ConflictError(
                    f"Asset {command.asset_id} is already a member of pool {existing.pool_id}."
                )
            member = AssetDepreciationPoolMember(
                pool_id=pool_id,
                asset_id=command.asset_id,
                joined_date=command.joined_date,
                left_date=None,
            )
            pool_repo.save_member(member)
            uow.commit()
            from seeker_accounting.modules.audit.event_type_catalog import ASSET_DEPRECIATION_POOL_MEMBER_ADDED
            self._record_audit(company_id, ASSET_DEPRECIATION_POOL_MEMBER_ADDED, "AssetDepreciationPool", pool_id, f"Added asset {command.asset_id} to pool id={pool_id}")
            # Expire all so the reload issues a fresh SELECT with selectinload
            uow.session.expire_all()
            pool = pool_repo.get_by_id(company_id, pool_id)
            return self._to_dto(pool)

    # ------------------------------------------------------------------

    def _validate_pool(self, code: str, name: str, pool_type: str, method: str, life: int) -> None:
        if not code or not code.strip():
            raise ValidationError("Pool code is required.")
        if not name or not name.strip():
            raise ValidationError("Pool name is required.")
        if pool_type not in _VALID_POOL_TYPES:
            raise ValidationError(f"Pool type must be one of: {', '.join(sorted(_VALID_POOL_TYPES))}.")
        if method not in _POOL_VALID_METHODS:
            raise ValidationError(
                f"Pool depreciation method '{method}' is not valid for pools. "
                f"Valid: {', '.join(sorted(_POOL_VALID_METHODS))}."
            )
        if life <= 0:
            raise ValidationError("Useful life months must be greater than zero.")

    def _require_company(self, session: Session, company_id: int) -> None:
        repo = self._company_repository_factory(session)
        if repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company {company_id} not found.")

    def _to_dto(self, pool: AssetDepreciationPool) -> AssetDepreciationPoolDTO:
        members = tuple(
            AssetDepreciationPoolMemberDTO(
                id=m.id,
                pool_id=m.pool_id,
                asset_id=m.asset_id,
                joined_date=m.joined_date,
                left_date=m.left_date,
            )
            for m in (pool.members or [])
        )
        return AssetDepreciationPoolDTO(
            id=pool.id,
            company_id=pool.company_id,
            code=pool.code,
            name=pool.name,
            pool_type_code=pool.pool_type_code,
            depreciation_method_code=pool.depreciation_method_code,
            useful_life_months=pool.useful_life_months,
            is_active=pool.is_active,
            created_at=pool.created_at,
            updated_at=pool.updated_at,
            members=members,
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
