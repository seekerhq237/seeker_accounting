from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.fixed_assets.dto.depreciation_commands import CreateDepreciationRunCommand
from seeker_accounting.modules.fixed_assets.dto.depreciation_dto import (
    AssetDepreciationRunDetailDTO,
    AssetDepreciationRunLineDTO,
    AssetDepreciationRunListItemDTO,
)
from seeker_accounting.modules.fixed_assets.models.asset_depreciation_run import AssetDepreciationRun
from seeker_accounting.modules.fixed_assets.models.asset_depreciation_run_line import AssetDepreciationRunLine
from seeker_accounting.modules.fixed_assets.repositories.asset_depreciation_run_repository import (
    AssetDepreciationRunRepository,
)
from seeker_accounting.modules.fixed_assets.repositories.asset_depreciation_run_line_repository import (
    AssetDepreciationRunLineRepository,
)
from seeker_accounting.modules.fixed_assets.repositories.asset_repository import AssetRepository
from seeker_accounting.modules.fixed_assets.services.depreciation_schedule_service import (
    DepreciationScheduleService,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

_ZERO = Decimal("0")

AssetRepositoryFactory = Callable[[Session], AssetRepository]
AssetDepreciationRunRepositoryFactory = Callable[[Session], AssetDepreciationRunRepository]
AssetDepreciationRunLineRepositoryFactory = Callable[[Session], AssetDepreciationRunLineRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]


class DepreciationRunService:
    DOCUMENT_TYPE_CODE = "DEPRECIATION_RUN"

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        asset_repository_factory: AssetRepositoryFactory,
        asset_depreciation_run_repository_factory: AssetDepreciationRunRepositoryFactory,
        asset_depreciation_run_line_repository_factory: AssetDepreciationRunLineRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        depreciation_schedule_service: DepreciationScheduleService,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._asset_repository_factory = asset_repository_factory
        self._asset_depreciation_run_repository_factory = asset_depreciation_run_repository_factory
        self._asset_depreciation_run_line_repository_factory = asset_depreciation_run_line_repository_factory
        self._company_repository_factory = company_repository_factory
        self._depreciation_schedule_service = depreciation_schedule_service
        self._audit_service = audit_service

    def list_depreciation_runs(
        self, company_id: int, status_code: str | None = None
    ) -> list[AssetDepreciationRunListItemDTO]:
        with self._unit_of_work_factory() as uow:
            run_repo = self._asset_depreciation_run_repository_factory(uow.session)
            line_repo = self._asset_depreciation_run_line_repository_factory(uow.session)
            runs = run_repo.list_by_company(company_id, status_code=status_code)
            if not runs:
                return []
            # Single aggregate query across all runs in this list — replaces
            # the previous per-run line fetch (N+1).
            totals = line_repo.aggregate_totals_by_run(run.id for run in runs)
            result = []
            for run in runs:
                asset_count, total = totals.get(run.id, (0, _ZERO))
                result.append(AssetDepreciationRunListItemDTO(
                    id=run.id,
                    company_id=run.company_id,
                    run_number=run.run_number,
                    run_date=run.run_date,
                    period_end_date=run.period_end_date,
                    status_code=run.status_code,
                    posted_at=run.posted_at,
                    asset_count=asset_count,
                    total_depreciation=total,
                ))
            return result

    def get_depreciation_run(
        self, company_id: int, run_id: int
    ) -> AssetDepreciationRunDetailDTO:
        with self._unit_of_work_factory() as uow:
            run_repo = self._asset_depreciation_run_repository_factory(uow.session)
            run = run_repo.get_by_id(company_id, run_id)
            if run is None:
                raise NotFoundError(f"Depreciation run {run_id} not found.")
            return self._to_detail_dto(run)

    def create_run(
        self, company_id: int, command: CreateDepreciationRunCommand
    ) -> AssetDepreciationRunDetailDTO:
        """Create a draft depreciation run, computing per-asset depreciation for period_end_date."""
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)

            run_repo = self._asset_depreciation_run_repository_factory(uow.session)
            asset_repo = self._asset_repository_factory(uow.session)
            line_repo = self._asset_depreciation_run_line_repository_factory(uow.session)

            # Only active assets eligible
            eligible_assets = asset_repo.list_eligible_for_run(company_id)
            if not eligible_assets:
                raise ValidationError("No active assets are eligible for depreciation in this company.")

            now = datetime.utcnow()
            run = AssetDepreciationRun(
                company_id=company_id,
                run_number=None,  # assigned on post
                run_date=command.run_date,
                period_end_date=command.period_end_date,
                status_code="draft",
                created_at=now,
            )
            run_repo.save(run)

            # Compute depreciation for each eligible asset
            for asset in eligible_assets:
                # Get total accumulated depreciation from prior posted runs
                accumulated_so_far = run_repo.get_total_depreciation_for_asset(asset.id)

                salvage = asset.salvage_value if asset.salvage_value is not None else _ZERO
                depreciable_base = asset.acquisition_cost - salvage

                # How much is still depreciable?
                remaining_depreciable = max(_ZERO, depreciable_base - accumulated_so_far)
                if remaining_depreciable <= _ZERO:
                    # Asset already fully depreciated — skip
                    continue

                # Generate the full schedule and find the period that covers period_end_date
                from seeker_accounting.modules.fixed_assets.dto.depreciation_commands import GenerateDepreciationScheduleCommand
                schedule_cmd = GenerateDepreciationScheduleCommand(
                    acquisition_cost=asset.acquisition_cost,
                    salvage_value=salvage,
                    useful_life_months=asset.useful_life_months,
                    depreciation_method_code=asset.depreciation_method_code,
                    capitalization_date=asset.capitalization_date,
                )
                schedule = self._depreciation_schedule_service.preview_schedule(schedule_cmd)

                # Determine which month slot covers period_end_date relative to capitalization
                from seeker_accounting.modules.fixed_assets.services._depreciation_period_helper import months_elapsed
                months_so_far = months_elapsed(asset.capitalization_date, command.period_end_date)
                if months_so_far <= 0 or months_so_far > len(schedule.lines):
                    # Not yet in service or past schedule end
                    continue

                # Find the schedule line for this period
                period_line = schedule.lines[months_so_far - 1]
                period_depr = period_line.depreciation_amount

                # Cap to remaining depreciable
                period_depr = min(period_depr, remaining_depreciable)
                if period_depr <= _ZERO:
                    continue

                accumulated_after = accumulated_so_far + period_depr
                nbv_after = max(asset.acquisition_cost - accumulated_after, salvage)

                run_line = AssetDepreciationRunLine(
                    asset_depreciation_run_id=run.id,
                    asset_id=asset.id,
                    depreciation_amount=period_depr,
                    accumulated_depreciation_after=accumulated_after,
                    net_book_value_after=nbv_after,
                )
                line_repo.save(run_line)

            uow.commit()
            # Reload for DTO
            run = run_repo.get_by_id(company_id, run.id)
            from seeker_accounting.modules.audit.event_type_catalog import DEPRECIATION_RUN_CREATED
            self._record_audit(company_id, DEPRECIATION_RUN_CREATED, "AssetDepreciationRun", run.id, "Created depreciation run")
            return self._to_detail_dto(run)

    def cancel_run(self, company_id: int, run_id: int) -> None:
        with self._unit_of_work_factory() as uow:
            run_repo = self._asset_depreciation_run_repository_factory(uow.session)
            run = run_repo.get_by_id(company_id, run_id)
            if run is None:
                raise NotFoundError(f"Depreciation run {run_id} not found.")
            if run.status_code != "draft":
                raise ValidationError("Only draft depreciation runs can be cancelled.")
            run.status_code = "cancelled"
            run_repo.save(run)
            uow.commit()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_company(self, session: Session, company_id: int) -> None:
        repo = self._company_repository_factory(session)
        if repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company {company_id} not found.")

    def _to_detail_dto(self, run: AssetDepreciationRun) -> AssetDepreciationRunDetailDTO:
        line_dtos = tuple(
            AssetDepreciationRunLineDTO(
                id=line.id,
                asset_id=line.asset_id,
                asset_number=line.asset.asset_number if line.asset else "",
                asset_name=line.asset.asset_name if line.asset else "",
                depreciation_amount=line.depreciation_amount,
                accumulated_depreciation_after=line.accumulated_depreciation_after,
                net_book_value_after=line.net_book_value_after,
            )
            for line in (run.lines or [])
        )
        total = sum(l.depreciation_amount for l in line_dtos)
        return AssetDepreciationRunDetailDTO(
            id=run.id,
            company_id=run.company_id,
            run_number=run.run_number,
            run_date=run.run_date,
            period_end_date=run.period_end_date,
            status_code=run.status_code,
            posted_journal_entry_id=run.posted_journal_entry_id,
            posted_at=run.posted_at,
            posted_by_user_id=run.posted_by_user_id,
            created_at=run.created_at,
            lines=line_dtos,
            asset_count=len(line_dtos),
            total_depreciation=total,
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
