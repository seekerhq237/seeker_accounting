from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.contracts_projects.models.project import Project
from seeker_accounting.modules.contracts_projects.repositories.project_repository import ProjectRepository
from seeker_accounting.modules.job_costing.dto.project_actual_cost_dto import (
    ProjectActualCostBreakdownDTO,
    ProjectActualCostBreakdownItemDTO,
    ProjectActualCostSourceTotalDTO,
    ProjectActualCostSummaryDTO,
)
from seeker_accounting.modules.job_costing.repositories.project_actuals_query_repository import (
    ProjectActualCostBreakdownRow,
    ProjectActualsQueryRepository,
)
from seeker_accounting.platform.exceptions import NotFoundError

ProjectRepositoryFactory = Callable[[Session], ProjectRepository]
ProjectActualsQueryRepositoryFactory = Callable[[Session], ProjectActualsQueryRepository]

_SOURCE_ORDER: tuple[tuple[str, str], ...] = (
    ("purchase_bill", "Purchase Bills"),
    ("treasury_payment", "Treasury Payments"),
    ("inventory_issue", "Inventory Issues"),
    ("payroll_allocation", "Payroll Allocations"),
    ("manual_journal", "Manual Journals"),
)


class ProjectActualCostService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        project_repository_factory: ProjectRepositoryFactory,
        actuals_query_repository_factory: ProjectActualsQueryRepositoryFactory,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._project_repository_factory = project_repository_factory
        self._actuals_query_repository_factory = actuals_query_repository_factory

    def get_actual_cost_summary(
        self,
        company_id: int,
        project_id: int,
    ) -> ProjectActualCostSummaryDTO:
        with self._unit_of_work_factory() as uow:
            project = self._require_project(uow.session, company_id, project_id)
            rows = self._actuals_query_repository_factory(uow.session).list_actual_cost_breakdown(
                company_id,
                project_id,
            )
            return self._build_summary(project, rows)

    def get_actual_cost_breakdown(
        self,
        company_id: int,
        project_id: int,
    ) -> ProjectActualCostBreakdownDTO:
        with self._unit_of_work_factory() as uow:
            project = self._require_project(uow.session, company_id, project_id)
            rows = self._actuals_query_repository_factory(uow.session).list_actual_cost_breakdown(
                company_id,
                project_id,
            )
            summary = self._build_summary(project, rows)
            items = tuple(self._to_breakdown_item_dto(row) for row in rows)
            return ProjectActualCostBreakdownDTO(summary=summary, items=items)

    def _require_project(self, session: Session, company_id: int, project_id: int) -> Project:
        project = self._project_repository_factory(session).get_by_company_and_id(company_id, project_id)
        if project is None:
            raise NotFoundError(f"Project with id {project_id} was not found.")
        return project

    def _build_summary(
        self,
        project: Project,
        rows: Iterable[ProjectActualCostBreakdownRow],
    ) -> ProjectActualCostSummaryDTO:
        totals = {code: Decimal("0.00") for code, _ in _SOURCE_ORDER}
        for row in rows:
            totals[row.source_type_code] = totals.get(row.source_type_code, Decimal("0.00")) + row.amount

        source_totals = tuple(
            ProjectActualCostSourceTotalDTO(
                source_type_code=code,
                source_type_label=label,
                amount=totals[code],
            )
            for code, label in _SOURCE_ORDER
        )
        total_actual_cost_amount = sum((item.amount for item in source_totals), Decimal("0.00"))
        contract = project.contract
        return ProjectActualCostSummaryDTO(
            project_id=project.id,
            project_code=project.project_code,
            project_name=project.project_name,
            contract_id=project.contract_id,
            contract_number=contract.contract_number if contract is not None else None,
            currency_code=project.currency_code,
            total_actual_cost_amount=total_actual_cost_amount,
            source_totals=source_totals,
        )

    @staticmethod
    def _to_breakdown_item_dto(row: ProjectActualCostBreakdownRow) -> ProjectActualCostBreakdownItemDTO:
        return ProjectActualCostBreakdownItemDTO(
            source_type_code=row.source_type_code,
            source_type_label=row.source_type_label,
            project_job_id=row.project_job_id,
            project_job_code=row.project_job_code,
            project_job_name=row.project_job_name,
            project_cost_code_id=row.project_cost_code_id,
            project_cost_code=row.project_cost_code,
            project_cost_code_name=row.project_cost_code_name,
            amount=row.amount,
        )