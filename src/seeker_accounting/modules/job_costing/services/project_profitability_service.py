from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.contracts_projects.models.project import Project
from seeker_accounting.modules.contracts_projects.repositories.project_repository import ProjectRepository
from seeker_accounting.modules.job_costing.dto.project_profitability_dto import (
    ProjectProfitabilityBreakdownItemDTO,
    ProjectProfitabilityDTO,
    ProjectProfitabilitySummaryDTO,
)
from seeker_accounting.modules.job_costing.repositories.project_actuals_query_repository import (
    ProjectActualsQueryRepository,
)
from seeker_accounting.modules.job_costing.repositories.project_profitability_query_repository import (
    ProjectDimensionAmountRow,
    ProjectProfitabilityQueryRepository,
)
from seeker_accounting.platform.exceptions import NotFoundError

ProjectRepositoryFactory = Callable[[Session], ProjectRepository]
ProjectActualsQueryRepositoryFactory = Callable[[Session], ProjectActualsQueryRepository]
ProjectProfitabilityQueryRepositoryFactory = Callable[[Session], ProjectProfitabilityQueryRepository]


@dataclass(frozen=True, slots=True)
class _DimensionKey:
    project_job_id: int | None
    project_job_code: str | None
    project_job_name: str | None
    project_cost_code_id: int | None
    project_cost_code: str | None
    project_cost_code_name: str | None


class ProjectProfitabilityService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        project_repository_factory: ProjectRepositoryFactory,
        actuals_query_repository_factory: ProjectActualsQueryRepositoryFactory,
        profitability_query_repository_factory: ProjectProfitabilityQueryRepositoryFactory,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._project_repository_factory = project_repository_factory
        self._actuals_query_repository_factory = actuals_query_repository_factory
        self._profitability_query_repository_factory = profitability_query_repository_factory

    def get_profitability(
        self,
        company_id: int,
        project_id: int,
    ) -> ProjectProfitabilityDTO:
        with self._unit_of_work_factory() as uow:
            project = self._require_project(uow.session, company_id, project_id)
            actual_rows = self._actuals_query_repository_factory(uow.session).list_actual_cost_by_dimension(
                company_id,
                project_id,
            )
            profitability_repo = self._profitability_query_repository_factory(uow.session)
            revenue_rows = profitability_repo.list_revenue_by_dimension(company_id, project_id)
            budget_rows = profitability_repo.list_current_budget_by_dimension(project_id)
            commitment_rows = profitability_repo.list_open_commitments_by_dimension(project_id)

            actual_by_dimension = self._index_rows(actual_rows)
            revenue_by_dimension = self._index_rows(revenue_rows)
            budget_by_dimension = self._index_rows(budget_rows)
            commitment_by_dimension = self._index_rows(commitment_rows)

            keys = sorted(
                set(actual_by_dimension) | set(revenue_by_dimension) | set(budget_by_dimension) | set(commitment_by_dimension),
                key=lambda item: (item.project_job_code or "", item.project_cost_code or ""),
            )
            items = tuple(
                self._build_breakdown_item(
                    key=key,
                    billed_revenue_amount=revenue_by_dimension.get(key, Decimal("0.00")),
                    actual_cost_amount=actual_by_dimension.get(key, Decimal("0.00")),
                    current_budget_amount=budget_by_dimension.get(key, Decimal("0.00")),
                    approved_open_commitment_amount=commitment_by_dimension.get(key, Decimal("0.00")),
                )
                for key in keys
            )

            billed_revenue_amount = sum(revenue_by_dimension.values(), Decimal("0.00"))
            actual_cost_amount = sum(actual_by_dimension.values(), Decimal("0.00"))
            current_budget_amount = sum(budget_by_dimension.values(), Decimal("0.00"))
            approved_open_commitment_amount = sum(commitment_by_dimension.values(), Decimal("0.00"))

            gross_profit_amount = billed_revenue_amount - actual_cost_amount
            budget_variance_amount = current_budget_amount - actual_cost_amount
            remaining_budget_amount = current_budget_amount - actual_cost_amount
            projected_margin_after_commitments_amount = (
                billed_revenue_amount - actual_cost_amount - approved_open_commitment_amount
            )
            remaining_budget_after_commitments_amount = (
                current_budget_amount - actual_cost_amount - approved_open_commitment_amount
            )
            gross_margin_percent = self._compute_margin_percent(
                gross_profit_amount,
                billed_revenue_amount,
            )

            contract = project.contract
            summary = ProjectProfitabilitySummaryDTO(
                project_id=project.id,
                project_code=project.project_code,
                project_name=project.project_name,
                contract_id=project.contract_id,
                contract_number=contract.contract_number if contract is not None else None,
                currency_code=project.currency_code,
                billed_revenue_amount=billed_revenue_amount,
                actual_cost_amount=actual_cost_amount,
                approved_open_commitment_amount=approved_open_commitment_amount,
                current_budget_amount=current_budget_amount,
                gross_profit_amount=gross_profit_amount,
                gross_margin_percent=gross_margin_percent,
                budget_variance_amount=budget_variance_amount,
                remaining_budget_amount=remaining_budget_amount,
                projected_margin_after_commitments_amount=projected_margin_after_commitments_amount,
                remaining_budget_after_commitments_amount=remaining_budget_after_commitments_amount,
            )
            return ProjectProfitabilityDTO(summary=summary, items=items)

    def _require_project(self, session: Session, company_id: int, project_id: int) -> Project:
        project = self._project_repository_factory(session).get_by_company_and_id(company_id, project_id)
        if project is None:
            raise NotFoundError(f"Project with id {project_id} was not found.")
        return project

    @staticmethod
    def _index_rows(rows: list[ProjectDimensionAmountRow]) -> dict[_DimensionKey, Decimal]:
        indexed: dict[_DimensionKey, Decimal] = {}
        for row in rows:
            key = _DimensionKey(
                project_job_id=row.project_job_id,
                project_job_code=row.project_job_code,
                project_job_name=row.project_job_name,
                project_cost_code_id=row.project_cost_code_id,
                project_cost_code=row.project_cost_code,
                project_cost_code_name=row.project_cost_code_name,
            )
            indexed[key] = indexed.get(key, Decimal("0.00")) + row.amount
        return indexed

    @staticmethod
    def _build_breakdown_item(
        *,
        key: _DimensionKey,
        billed_revenue_amount: Decimal,
        actual_cost_amount: Decimal,
        current_budget_amount: Decimal,
        approved_open_commitment_amount: Decimal,
    ) -> ProjectProfitabilityBreakdownItemDTO:
        gross_profit_amount = billed_revenue_amount - actual_cost_amount
        budget_variance_amount = current_budget_amount - actual_cost_amount
        remaining_budget_after_commitments_amount = (
            current_budget_amount - actual_cost_amount - approved_open_commitment_amount
        )
        return ProjectProfitabilityBreakdownItemDTO(
            project_job_id=key.project_job_id,
            project_job_code=key.project_job_code,
            project_job_name=key.project_job_name,
            project_cost_code_id=key.project_cost_code_id,
            project_cost_code=key.project_cost_code,
            project_cost_code_name=key.project_cost_code_name,
            billed_revenue_amount=billed_revenue_amount,
            actual_cost_amount=actual_cost_amount,
            current_budget_amount=current_budget_amount,
            approved_open_commitment_amount=approved_open_commitment_amount,
            gross_profit_amount=gross_profit_amount,
            budget_variance_amount=budget_variance_amount,
            remaining_budget_after_commitments_amount=remaining_budget_after_commitments_amount,
        )

    @staticmethod
    def _compute_margin_percent(
        gross_profit_amount: Decimal,
        billed_revenue_amount: Decimal,
    ) -> Decimal | None:
        if billed_revenue_amount == Decimal("0.00"):
            return None
        return ((gross_profit_amount / billed_revenue_amount) * Decimal("100")).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )