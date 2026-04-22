from __future__ import annotations

from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.fixed_assets.dto.depreciation_method_dto import DepreciationMethodDTO, MacrsProfileDTO
from seeker_accounting.modules.fixed_assets.models.depreciation_method import DepreciationMethod
from seeker_accounting.modules.fixed_assets.repositories.depreciation_method_repository import (
    DepreciationMethodRepository,
)
from seeker_accounting.modules.fixed_assets.repositories.macrs_profile_repository import MacrsProfileRepository
from seeker_accounting.platform.exceptions import NotFoundError

DepreciationMethodRepositoryFactory = Callable[[Session], DepreciationMethodRepository]
MacrsProfileRepositoryFactory = Callable[[Session], MacrsProfileRepository]


class DepreciationMethodService:
    """Read-only service for the seeded depreciation method catalog.

    The catalog is global (not company-scoped). It is seeded by Revision K and
    is never modified at runtime.
    """

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        depreciation_method_repository_factory: DepreciationMethodRepositoryFactory,
        macrs_profile_repository_factory: MacrsProfileRepositoryFactory | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._depreciation_method_repository_factory = depreciation_method_repository_factory
        self._macrs_profile_repository_factory = macrs_profile_repository_factory

    def list_methods(self, active_only: bool = True) -> list[DepreciationMethodDTO]:
        with self._unit_of_work_factory() as uow:
            repo = self._depreciation_method_repository_factory(uow.session)
            rows = repo.list_all(active_only=active_only)
            return [self._to_dto(m) for m in rows]

    def get_method(self, code: str) -> DepreciationMethodDTO:
        with self._unit_of_work_factory() as uow:
            repo = self._depreciation_method_repository_factory(uow.session)
            m = repo.get_by_code(code)
            if m is None:
                raise NotFoundError(f"Depreciation method '{code}' not found in catalog.")
            return self._to_dto(m)

    def list_macrs_profiles(self, active_only: bool = True) -> list[MacrsProfileDTO]:
        if self._macrs_profile_repository_factory is None:
            return []
        with self._unit_of_work_factory() as uow:
            repo = self._macrs_profile_repository_factory(uow.session)
            rows = repo.list_all(active_only=active_only)
            return [
                MacrsProfileDTO(
                    id=r.id,
                    class_code=r.class_code,
                    class_name=r.class_name,
                    recovery_period_years=r.recovery_period_years,
                    convention_code=r.convention_code,
                )
                for r in rows
            ]

    def _to_dto(self, m: DepreciationMethod) -> DepreciationMethodDTO:
        return DepreciationMethodDTO(
            id=m.id,
            code=m.code,
            name=m.name,
            asset_family_code=m.asset_family_code,
            requires_settings=m.requires_settings,
            requires_components=m.requires_components,
            requires_usage_records=m.requires_usage_records,
            requires_pool=m.requires_pool,
            requires_depletion_profile=m.requires_depletion_profile,
            has_switch_to_sl=m.has_switch_to_sl,
            sort_order=m.sort_order,
            is_active=m.is_active,
        )
