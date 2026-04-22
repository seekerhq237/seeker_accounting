from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.contracts_projects.models.contract import Contract
from seeker_accounting.modules.contracts_projects.repositories.contract_repository import ContractRepository
from seeker_accounting.modules.job_costing.repositories.project_actuals_query_repository import (
    ProjectActualsQueryRepository,
)
from seeker_accounting.modules.job_costing.repositories.project_profitability_query_repository import (
    ProjectProfitabilityQueryRepository,
)
from seeker_accounting.modules.management_reporting.dto.contract_summary_dto import (
    ContractProjectRollupItemDTO,
    ContractSummaryDTO,
)
from seeker_accounting.modules.management_reporting.repositories.contract_reporting_repository import (
    ContractReportingRepository,
)
from seeker_accounting.platform.exceptions import NotFoundError

ContractRepositoryFactory = Callable[[Session], ContractRepository]
ContractReportingRepositoryFactory = Callable[[Session], ContractReportingRepository]
ProjectActualsQueryRepositoryFactory = Callable[[Session], ProjectActualsQueryRepository]
ProjectProfitabilityQueryRepositoryFactory = Callable[[Session], ProjectProfitabilityQueryRepository]

_ZERO = Decimal("0.00")


class ContractReportingService:
    """Read-only management reporting service for contracts.

    Assembles contract financial summaries by aggregating project-level data
    from the Slice 16.1 query layer. No operational state is mutated.
    """

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        contract_repository_factory: ContractRepositoryFactory,
        contract_reporting_repository_factory: ContractReportingRepositoryFactory,
        actuals_query_repository_factory: ProjectActualsQueryRepositoryFactory,
        profitability_query_repository_factory: ProjectProfitabilityQueryRepositoryFactory,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._contract_repository_factory = contract_repository_factory
        self._contract_reporting_repository_factory = contract_reporting_repository_factory
        self._actuals_query_repository_factory = actuals_query_repository_factory
        self._profitability_query_repository_factory = profitability_query_repository_factory

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_contract_summary(self, company_id: int, contract_id: int) -> ContractSummaryDTO:
        """Return the complete financial summary for a single contract."""
        with self._unit_of_work_factory() as uow:
            contract = self._require_contract(uow.session, company_id, contract_id)
            return self._build_contract_summary(uow.session, contract, company_id)

    def list_contract_summaries(self, company_id: int) -> list[ContractSummaryDTO]:
        """Return financial summaries for all contracts belonging to a company.

        Each summary rolls up all linked projects. For companies with many
        contracts this iterates N contracts × M projects within a single
        session, which is acceptable for a reporting endpoint.
        """
        with self._unit_of_work_factory() as uow:
            contracts = self._contract_repository_factory(uow.session).list_by_company(company_id)
            return [
                self._build_contract_summary(uow.session, contract, company_id)
                for contract in contracts
            ]

    def get_contract_project_rollup(
        self, company_id: int, contract_id: int
    ) -> tuple[ContractProjectRollupItemDTO, ...]:
        """Return the per-project rollup items for a contract without the contract header."""
        with self._unit_of_work_factory() as uow:
            contract = self._require_contract(uow.session, company_id, contract_id)
            return self._build_rollup_items(uow.session, contract.id, company_id)

    # ------------------------------------------------------------------
    # Internal builders
    # ------------------------------------------------------------------

    def _build_contract_summary(
        self,
        session: Session,
        contract: Contract,
        company_id: int,
    ) -> ContractSummaryDTO:
        reporting_repo = self._contract_reporting_repository_factory(session)
        change_order_delta = reporting_repo.sum_approved_change_order_delta(contract.id)
        base_amount = contract.base_contract_amount or _ZERO
        current_contract_amount = base_amount + change_order_delta

        rollup_items = self._build_rollup_items(session, contract.id, company_id)

        total_revenue = sum((item.billed_revenue_amount for item in rollup_items), _ZERO)
        total_actual = sum((item.actual_cost_amount for item in rollup_items), _ZERO)
        total_commitment = sum((item.approved_commitment_amount for item in rollup_items), _ZERO)
        total_budget = sum((item.current_budget_amount for item in rollup_items), _ZERO)
        total_exposure = sum((item.total_exposure_amount for item in rollup_items), _ZERO)
        total_margin = total_revenue - total_actual
        total_margin_percent = self._compute_margin_percent(total_margin, total_revenue)

        return ContractSummaryDTO(
            company_id=company_id,
            contract_id=contract.id,
            contract_number=contract.contract_number,
            contract_title=contract.contract_title,
            currency_code=contract.currency_code,
            status_code=contract.status_code,
            contract_type_code=contract.contract_type_code,
            base_contract_amount=base_amount,
            approved_change_order_delta_total=change_order_delta,
            current_contract_amount=current_contract_amount,
            project_rollup_items=rollup_items,
            total_billed_revenue_amount=total_revenue,
            total_actual_cost_amount=total_actual,
            total_approved_commitment_amount=total_commitment,
            total_current_budget_amount=total_budget,
            total_exposure_amount=total_exposure,
            total_margin_amount=total_margin,
            total_margin_percent=total_margin_percent,
        )

    def _build_rollup_items(
        self,
        session: Session,
        contract_id: int,
        company_id: int,
    ) -> tuple[ContractProjectRollupItemDTO, ...]:
        reporting_repo = self._contract_reporting_repository_factory(session)
        actuals_repo = self._actuals_query_repository_factory(session)
        profitability_repo = self._profitability_query_repository_factory(session)

        projects = reporting_repo.list_projects_by_contract(company_id, contract_id)
        items: list[ContractProjectRollupItemDTO] = []
        for project in projects:
            actual_cost = sum(
                (r.amount for r in actuals_repo.list_actual_cost_by_dimension(company_id, project.id)),
                _ZERO,
            )
            billed_revenue = sum(
                (r.amount for r in profitability_repo.list_revenue_by_dimension(company_id, project.id)),
                _ZERO,
            )
            approved_commitment = sum(
                (r.amount for r in profitability_repo.list_open_commitments_by_dimension(project.id)),
                _ZERO,
            )
            current_budget = sum(
                (r.amount for r in profitability_repo.list_current_budget_by_dimension(project.id)),
                _ZERO,
            )
            total_exposure = actual_cost + approved_commitment
            remaining_after_commitments = current_budget - actual_cost - approved_commitment
            margin = billed_revenue - actual_cost
            margin_percent = self._compute_margin_percent(margin, billed_revenue)

            items.append(
                ContractProjectRollupItemDTO(
                    project_id=project.id,
                    project_code=project.project_code,
                    project_name=project.project_name,
                    currency_code=project.currency_code,
                    billed_revenue_amount=billed_revenue,
                    actual_cost_amount=actual_cost,
                    approved_commitment_amount=approved_commitment,
                    current_budget_amount=current_budget,
                    total_exposure_amount=total_exposure,
                    remaining_budget_after_commitments_amount=remaining_after_commitments,
                    margin_amount=margin,
                    margin_percent=margin_percent,
                )
            )
        return tuple(items)

    def _require_contract(
        self, session: Session, company_id: int, contract_id: int
    ) -> Contract:
        contract = self._contract_repository_factory(session).get_by_company_and_id(
            company_id, contract_id
        )
        if contract is None:
            raise NotFoundError(f"Contract with id {contract_id} was not found.")
        return contract

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
