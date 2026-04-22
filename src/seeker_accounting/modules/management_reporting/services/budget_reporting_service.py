from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.contracts_projects.models.project import Project
from seeker_accounting.modules.contracts_projects.repositories.project_repository import ProjectRepository
from seeker_accounting.modules.job_costing.repositories.project_actuals_query_repository import (
    ProjectActualsQueryRepository,
)
from seeker_accounting.modules.job_costing.repositories.project_profitability_query_repository import (
    ProjectDimensionAmountRow,
    ProjectProfitabilityQueryRepository,
)
from seeker_accounting.modules.management_reporting.dto.budget_variance_report_dto import (
    ProjectControlSummaryDTO,
    ProjectTrendSeriesDTO,
    ProjectTrendSeriesPointDTO,
    ProjectVarianceBreakdownItemDTO,
    ProjectVarianceSummaryDTO,
)
from seeker_accounting.modules.management_reporting.repositories.budget_reporting_repository import (
    BudgetReportingRepository,
    PeriodAmountRow,
)
from seeker_accounting.platform.exceptions import NotFoundError

ProjectRepositoryFactory = Callable[[Session], ProjectRepository]
ProjectActualsQueryRepositoryFactory = Callable[[Session], ProjectActualsQueryRepository]
ProjectProfitabilityQueryRepositoryFactory = Callable[[Session], ProjectProfitabilityQueryRepository]
BudgetReportingRepositoryFactory = Callable[[Session], BudgetReportingRepository]

_ZERO = Decimal("0.00")


@dataclass(frozen=True, slots=True)
class _DimensionKey:
    """Hashable key for cross-source dimension alignment."""

    project_job_id: int | None
    project_job_code: str | None
    project_job_name: str | None
    project_cost_code_id: int | None
    project_cost_code: str | None
    project_cost_code_name: str | None


@dataclass(frozen=True, slots=True)
class _CostCodeKey:
    """Collapsed key grouping by cost code only (aggregating across jobs)."""

    project_cost_code_id: int | None
    project_cost_code: str | None
    project_cost_code_name: str | None


@dataclass(frozen=True, slots=True)
class _JobKey:
    """Collapsed key grouping by job only (aggregating across cost codes)."""

    project_job_id: int | None
    project_job_code: str | None
    project_job_name: str | None


class BudgetReportingService:
    """Read-only management reporting service for budget variance and control analysis.

    Assembles variance summaries, dimension breakdowns, project control metrics,
    and chart-ready trend series from the Slice 16.1 query layer.

    No operational state is mutated. All output derives from approved/posted facts.
    """

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        project_repository_factory: ProjectRepositoryFactory,
        actuals_query_repository_factory: ProjectActualsQueryRepositoryFactory,
        profitability_query_repository_factory: ProjectProfitabilityQueryRepositoryFactory,
        budget_reporting_repository_factory: BudgetReportingRepositoryFactory,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._project_repository_factory = project_repository_factory
        self._actuals_query_repository_factory = actuals_query_repository_factory
        self._profitability_query_repository_factory = profitability_query_repository_factory
        self._budget_reporting_repository_factory = budget_reporting_repository_factory

    # ------------------------------------------------------------------
    # Public API — single project
    # ------------------------------------------------------------------

    def get_project_variance_summary(
        self, company_id: int, project_id: int
    ) -> ProjectVarianceSummaryDTO:
        """Return the full variance summary for a project."""
        with self._unit_of_work_factory() as uow:
            project = self._require_project(uow.session, company_id, project_id)
            totals = self._load_project_totals(uow.session, company_id, project_id)
            return self._build_variance_summary(project, totals)

    def get_project_variance_by_cost_code(
        self, company_id: int, project_id: int
    ) -> tuple[ProjectVarianceBreakdownItemDTO, ...]:
        """Return variance breakdown items aggregated by cost code across all jobs."""
        with self._unit_of_work_factory() as uow:
            self._require_project(uow.session, company_id, project_id)
            return self._load_variance_by_cost_code(uow.session, company_id, project_id)

    def get_project_variance_by_job(
        self, company_id: int, project_id: int
    ) -> tuple[ProjectVarianceBreakdownItemDTO, ...]:
        """Return variance breakdown items aggregated by job across all cost codes."""
        with self._unit_of_work_factory() as uow:
            self._require_project(uow.session, company_id, project_id)
            return self._load_variance_by_job(uow.session, company_id, project_id)

    def get_project_control_summary(
        self, company_id: int, project_id: int
    ) -> ProjectControlSummaryDTO:
        """Return the comprehensive project control summary."""
        with self._unit_of_work_factory() as uow:
            project = self._require_project(uow.session, company_id, project_id)
            totals = self._load_project_totals(uow.session, company_id, project_id)
            return self._build_control_summary(project, totals)

    def get_chart_trend_series(
        self, company_id: int, project_id: int
    ) -> ProjectTrendSeriesDTO:
        """Return chart-ready monthly cost/revenue trend series for a project."""
        with self._unit_of_work_factory() as uow:
            project = self._require_project(uow.session, company_id, project_id)
            budget_rows = self._profitability_query_repository_factory(
                uow.session
            ).list_current_budget_by_dimension(project_id)
            current_budget = sum((r.amount for r in budget_rows), _ZERO)

            budget_repo = self._budget_reporting_repository_factory(uow.session)
            cost_by_period = budget_repo.list_actual_cost_by_period(company_id, project_id)
            revenue_by_period = budget_repo.list_revenue_by_period(company_id, project_id)
            points = self._build_trend_points(cost_by_period, revenue_by_period)

            return ProjectTrendSeriesDTO(
                project_id=project.id,
                project_code=project.project_code,
                project_name=project.project_name,
                currency_code=project.currency_code,
                current_budget_amount=current_budget,
                points=points,
            )

    # ------------------------------------------------------------------
    # Public API — company-wide list
    # ------------------------------------------------------------------

    def list_project_control_summaries(self, company_id: int) -> list[ProjectControlSummaryDTO]:
        """Return control summaries for every project in a company.

        All queries run within a single session to avoid repeated connection
        overhead. Callers should expect N × 5 queries for N projects.
        """
        with self._unit_of_work_factory() as uow:
            projects = self._project_repository_factory(uow.session).list_by_company(company_id)
            return [
                self._build_control_summary(
                    project,
                    self._load_project_totals(uow.session, company_id, project.id),
                )
                for project in projects
            ]

    # ------------------------------------------------------------------
    # Internal data loading
    # ------------------------------------------------------------------

    def _load_project_totals(
        self,
        session: Session,
        company_id: int,
        project_id: int,
    ) -> _ProjectTotals:
        actuals_repo = self._actuals_query_repository_factory(session)
        profitability_repo = self._profitability_query_repository_factory(session)

        actual_rows = actuals_repo.list_actual_cost_by_dimension(company_id, project_id)
        revenue_rows = profitability_repo.list_revenue_by_dimension(company_id, project_id)
        budget_rows = profitability_repo.list_current_budget_by_dimension(project_id)
        commitment_rows = profitability_repo.list_open_commitments_by_dimension(project_id)

        actual_cost = sum((r.amount for r in actual_rows), _ZERO)
        billed_revenue = sum((r.amount for r in revenue_rows), _ZERO)
        current_budget = sum((r.amount for r in budget_rows), _ZERO)
        open_commitment = sum((r.amount for r in commitment_rows), _ZERO)

        return _ProjectTotals(
            actual_cost=actual_cost,
            billed_revenue=billed_revenue,
            current_budget=current_budget,
            open_commitment=open_commitment,
            actual_rows=actual_rows,
            budget_rows=budget_rows,
            commitment_rows=commitment_rows,
        )

    def _load_variance_by_cost_code(
        self,
        session: Session,
        company_id: int,
        project_id: int,
    ) -> tuple[ProjectVarianceBreakdownItemDTO, ...]:
        actuals_repo = self._actuals_query_repository_factory(session)
        profitability_repo = self._profitability_query_repository_factory(session)

        actual_rows = actuals_repo.list_actual_cost_by_dimension(company_id, project_id)
        budget_rows = profitability_repo.list_current_budget_by_dimension(project_id)
        commitment_rows = profitability_repo.list_open_commitments_by_dimension(project_id)

        actual_by_cc = self._index_by_cost_code(actual_rows)
        budget_by_cc = self._index_by_cost_code(budget_rows)
        commitment_by_cc = self._index_by_cost_code(commitment_rows)

        keys: list[_CostCodeKey] = sorted(
            set(actual_by_cc) | set(budget_by_cc) | set(commitment_by_cc),
            key=lambda k: k.project_cost_code or "",
        )
        return tuple(
            self._build_breakdown_item(
                job_id=None,
                job_code=None,
                job_name=None,
                cc_id=key.project_cost_code_id,
                cc_code=key.project_cost_code,
                cc_name=key.project_cost_code_name,
                approved_budget=budget_by_cc.get(key, _ZERO),
                actual_cost=actual_by_cc.get(key, _ZERO),
                approved_commitment=commitment_by_cc.get(key, _ZERO),
            )
            for key in keys
        )

    def _load_variance_by_job(
        self,
        session: Session,
        company_id: int,
        project_id: int,
    ) -> tuple[ProjectVarianceBreakdownItemDTO, ...]:
        actuals_repo = self._actuals_query_repository_factory(session)
        profitability_repo = self._profitability_query_repository_factory(session)

        actual_rows = actuals_repo.list_actual_cost_by_dimension(company_id, project_id)
        budget_rows = profitability_repo.list_current_budget_by_dimension(project_id)
        commitment_rows = profitability_repo.list_open_commitments_by_dimension(project_id)

        actual_by_job = self._index_by_job(actual_rows)
        budget_by_job = self._index_by_job(budget_rows)
        commitment_by_job = self._index_by_job(commitment_rows)

        keys: list[_JobKey] = sorted(
            set(actual_by_job) | set(budget_by_job) | set(commitment_by_job),
            key=lambda k: k.project_job_code or "",
        )
        return tuple(
            self._build_breakdown_item(
                job_id=key.project_job_id,
                job_code=key.project_job_code,
                job_name=key.project_job_name,
                cc_id=None,
                cc_code=None,
                cc_name=None,
                approved_budget=budget_by_job.get(key, _ZERO),
                actual_cost=actual_by_job.get(key, _ZERO),
                approved_commitment=commitment_by_job.get(key, _ZERO),
            )
            for key in keys
        )

    # ------------------------------------------------------------------
    # DTO builders
    # ------------------------------------------------------------------

    def _build_variance_summary(
        self,
        project: Project,
        totals: _ProjectTotals,
    ) -> ProjectVarianceSummaryDTO:
        total_exposure = totals.actual_cost + totals.open_commitment
        remaining_budget = totals.current_budget - totals.actual_cost
        remaining_after_commitments = totals.current_budget - totals.actual_cost - totals.open_commitment
        variance = totals.current_budget - totals.actual_cost
        variance_percent = self._compute_variance_percent(variance, totals.current_budget)
        margin = totals.billed_revenue - totals.actual_cost
        margin_percent = self._compute_margin_percent(margin, totals.billed_revenue)
        contract = project.contract
        return ProjectVarianceSummaryDTO(
            project_id=project.id,
            project_code=project.project_code,
            project_name=project.project_name,
            contract_id=project.contract_id,
            contract_number=contract.contract_number if contract is not None else None,
            currency_code=project.currency_code,
            approved_budget_amount=totals.current_budget,
            actual_cost_amount=totals.actual_cost,
            approved_commitment_amount=totals.open_commitment,
            total_exposure_amount=total_exposure,
            remaining_budget_amount=remaining_budget,
            remaining_budget_after_commitments_amount=remaining_after_commitments,
            variance_amount=variance,
            variance_percent=variance_percent,
            billed_revenue_amount=totals.billed_revenue,
            margin_amount=margin,
            margin_percent=margin_percent,
        )

    def _build_control_summary(
        self,
        project: Project,
        totals: _ProjectTotals,
    ) -> ProjectControlSummaryDTO:
        total_exposure = totals.actual_cost + totals.open_commitment
        remaining_budget = totals.current_budget - totals.actual_cost
        remaining_after_commitments = totals.current_budget - totals.actual_cost - totals.open_commitment
        variance = totals.current_budget - totals.actual_cost
        variance_percent = self._compute_variance_percent(variance, totals.current_budget)
        gross_margin = totals.billed_revenue - totals.actual_cost
        gross_margin_percent = self._compute_margin_percent(gross_margin, totals.billed_revenue)
        contract = project.contract
        return ProjectControlSummaryDTO(
            project_id=project.id,
            project_code=project.project_code,
            project_name=project.project_name,
            contract_id=project.contract_id,
            contract_number=contract.contract_number if contract is not None else None,
            currency_code=project.currency_code,
            current_budget_amount=totals.current_budget,
            actual_cost_amount=totals.actual_cost,
            approved_open_commitment_amount=totals.open_commitment,
            total_exposure_amount=total_exposure,
            remaining_budget_amount=remaining_budget,
            remaining_budget_after_commitments_amount=remaining_after_commitments,
            variance_amount=variance,
            variance_percent=variance_percent,
            billed_revenue_amount=totals.billed_revenue,
            gross_margin_amount=gross_margin,
            gross_margin_percent=gross_margin_percent,
        )

    @staticmethod
    def _build_breakdown_item(
        *,
        job_id: int | None,
        job_code: str | None,
        job_name: str | None,
        cc_id: int | None,
        cc_code: str | None,
        cc_name: str | None,
        approved_budget: Decimal,
        actual_cost: Decimal,
        approved_commitment: Decimal,
    ) -> ProjectVarianceBreakdownItemDTO:
        total_exposure = actual_cost + approved_commitment
        remaining_budget = approved_budget - actual_cost
        variance = approved_budget - actual_cost
        variance_percent: Decimal | None
        if approved_budget == _ZERO:
            variance_percent = None
        else:
            variance_percent = ((variance / approved_budget) * Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        return ProjectVarianceBreakdownItemDTO(
            project_job_id=job_id,
            project_job_code=job_code,
            project_job_name=job_name,
            project_cost_code_id=cc_id,
            project_cost_code=cc_code,
            project_cost_code_name=cc_name,
            approved_budget_amount=approved_budget,
            actual_cost_amount=actual_cost,
            approved_commitment_amount=approved_commitment,
            total_exposure_amount=total_exposure,
            remaining_budget_amount=remaining_budget,
            variance_amount=variance,
            variance_percent=variance_percent,
        )

    @staticmethod
    def _build_trend_points(
        cost_rows: list[PeriodAmountRow],
        revenue_rows: list[PeriodAmountRow],
    ) -> tuple[ProjectTrendSeriesPointDTO, ...]:
        cost_map: dict[tuple[int, int], Decimal] = {
            (r.period_year, r.period_month): r.amount for r in cost_rows
        }
        revenue_map: dict[tuple[int, int], Decimal] = {
            (r.period_year, r.period_month): r.amount for r in revenue_rows
        }
        all_periods = sorted(set(cost_map) | set(revenue_map))
        points: list[ProjectTrendSeriesPointDTO] = []
        cumulative_cost = _ZERO
        cumulative_revenue = _ZERO
        for year, month in all_periods:
            cost_amt = cost_map.get((year, month), _ZERO)
            revenue_amt = revenue_map.get((year, month), _ZERO)
            cumulative_cost = cumulative_cost + cost_amt
            cumulative_revenue = cumulative_revenue + revenue_amt
            points.append(
                ProjectTrendSeriesPointDTO(
                    period_label=f"{year:04d}-{month:02d}",
                    period_year=year,
                    period_month=month,
                    actual_cost_amount=cost_amt,
                    cumulative_actual_cost_amount=cumulative_cost,
                    billed_revenue_amount=revenue_amt,
                    cumulative_billed_revenue_amount=cumulative_revenue,
                )
            )
        return tuple(points)

    # ------------------------------------------------------------------
    # Indexing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _index_by_cost_code(
        rows: list[ProjectDimensionAmountRow],
    ) -> dict[_CostCodeKey, Decimal]:
        result: dict[_CostCodeKey, Decimal] = {}
        for row in rows:
            key = _CostCodeKey(
                project_cost_code_id=row.project_cost_code_id,
                project_cost_code=row.project_cost_code,
                project_cost_code_name=row.project_cost_code_name,
            )
            result[key] = result.get(key, _ZERO) + row.amount
        return result

    @staticmethod
    def _index_by_job(
        rows: list[ProjectDimensionAmountRow],
    ) -> dict[_JobKey, Decimal]:
        result: dict[_JobKey, Decimal] = {}
        for row in rows:
            key = _JobKey(
                project_job_id=row.project_job_id,
                project_job_code=row.project_job_code,
                project_job_name=row.project_job_name,
            )
            result[key] = result.get(key, _ZERO) + row.amount
        return result

    # ------------------------------------------------------------------
    # Percent calculations
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_variance_percent(
        variance_amount: Decimal,
        approved_budget: Decimal,
    ) -> Decimal | None:
        if approved_budget == _ZERO:
            return None
        return ((variance_amount / approved_budget) * Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    @staticmethod
    def _compute_margin_percent(
        margin_amount: Decimal,
        revenue_amount: Decimal,
    ) -> Decimal | None:
        if revenue_amount == _ZERO:
            return None
        return ((margin_amount / revenue_amount) * Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    def _require_project(
        self, session: Session, company_id: int, project_id: int
    ) -> Project:
        project = self._project_repository_factory(session).get_by_company_and_id(
            company_id, project_id
        )
        if project is None:
            raise NotFoundError(f"Project with id {project_id} was not found.")
        return project


@dataclass(slots=True)
class _ProjectTotals:
    """Internal value object holding pre-loaded totals for a project."""

    actual_cost: Decimal
    billed_revenue: Decimal
    current_budget: Decimal
    open_commitment: Decimal
    actual_rows: list[ProjectDimensionAmountRow]
    budget_rows: list[ProjectDimensionAmountRow]
    commitment_rows: list[ProjectDimensionAmountRow]
