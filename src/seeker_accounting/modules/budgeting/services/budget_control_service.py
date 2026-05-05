from __future__ import annotations

from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.budgeting.dto.budget_control_dto import BudgetControlCheckDTO
from seeker_accounting.modules.budgeting.repositories.project_budget_line_repository import (
    ProjectBudgetLineRepository,
)
from seeker_accounting.modules.budgeting.repositories.project_budget_version_repository import (
    ProjectBudgetVersionRepository,
)
from seeker_accounting.modules.contracts_projects.repositories.project_repository import ProjectRepository
from seeker_accounting.modules.job_costing.repositories.project_actuals_query_repository import (
    ProjectActualsQueryRepository,
)
from seeker_accounting.modules.job_costing.repositories.project_commitment_line_repository import (
    ProjectCommitmentLineRepository,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

ProjectBudgetVersionRepositoryFactory = Callable[[Session], ProjectBudgetVersionRepository]
ProjectBudgetLineRepositoryFactory = Callable[[Session], ProjectBudgetLineRepository]
ProjectRepositoryFactory = Callable[[Session], ProjectRepository]
ProjectCommitmentLineRepositoryFactory = Callable[[Session], ProjectCommitmentLineRepository]
ProjectActualsQueryRepositoryFactory = Callable[[Session], ProjectActualsQueryRepository]

_ZERO = Decimal("0.00")
_CONTROL_MODES = {"none", "warn", "hard_stop"}


class BudgetControlService:
    """Check budget availability against approved budgets, commitments, and posted actuals."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        version_repository_factory: ProjectBudgetVersionRepositoryFactory,
        line_repository_factory: ProjectBudgetLineRepositoryFactory,
        project_repository_factory: ProjectRepositoryFactory,
        commitment_line_repository_factory: ProjectCommitmentLineRepositoryFactory,
        actuals_query_repository_factory: ProjectActualsQueryRepositoryFactory,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._version_repository_factory = version_repository_factory
        self._line_repository_factory = line_repository_factory
        self._project_repository_factory = project_repository_factory
        self._commitment_line_repository_factory = commitment_line_repository_factory
        self._actuals_query_repository_factory = actuals_query_repository_factory

    def check_budget(
        self,
        project_id: int,
        requested_amount: Decimal,
        *,
        project_job_id: int | None = None,
        project_cost_code_id: int | None = None,
        exclude_commitment_id: int | None = None,
    ) -> BudgetControlCheckDTO:
        """Return a budget control check for a project/dimension request."""
        with self._unit_of_work_factory() as uow:
            project_repo = self._project_repository_factory(uow.session)
            project = project_repo.get_by_id(project_id)
            if project is None:
                raise NotFoundError(f"Project {project_id} not found.")

            control_mode = self._normalize_control_mode(project.budget_control_mode_code)
            amount = self._to_money(requested_amount)

            version_repo = self._version_repository_factory(uow.session)
            approved = version_repo.get_current_approved(project_id)
            committed = self._commitment_line_repository_factory(
                uow.session
            ).sum_open_by_project_dimension(
                project_id=project_id,
                project_job_id=project_job_id,
                project_cost_code_id=project_cost_code_id,
                exclude_commitment_id=exclude_commitment_id,
            )
            actual = self._actuals_query_repository_factory(
                uow.session
            ).sum_actual_by_project_dimension(
                company_id=project.company_id,
                project_id=project_id,
                project_job_id=project_job_id,
                project_cost_code_id=project_cost_code_id,
            )

            if approved is None:
                remaining_after = _ZERO - amount
                would_exceed = amount > _ZERO
                return BudgetControlCheckDTO(
                    project_id=project_id,
                    budget_version_id=None,
                    budget_total=_ZERO,
                    control_mode=control_mode,
                    requested_amount=amount,
                    committed_amount=committed,
                    actual_amount=actual,
                    remaining_before_request=_ZERO,
                    remaining_after_request=remaining_after,
                    would_exceed_budget=would_exceed and control_mode != "none",
                    message=self._build_message(control_mode, would_exceed, remaining_after, no_budget=True),
                    project_job_id=project_job_id,
                    project_cost_code_id=project_cost_code_id,
                )

            budget_total = self._resolve_budget_total(
                uow.session,
                version_id=approved.id,
                version_total=approved.total_budget_amount,
                project_job_id=project_job_id,
                project_cost_code_id=project_cost_code_id,
            )
            consumed = committed + actual
            remaining_before = budget_total - consumed
            remaining_after = remaining_before - amount
            would_exceed = remaining_after < _ZERO

            return BudgetControlCheckDTO(
                project_id=project_id,
                budget_version_id=approved.id,
                budget_total=budget_total,
                control_mode=control_mode,
                requested_amount=amount,
                committed_amount=committed,
                actual_amount=actual,
                remaining_before_request=remaining_before,
                remaining_after_request=remaining_after,
                would_exceed_budget=would_exceed and control_mode != "none",
                message=self._build_message(control_mode, would_exceed, remaining_after),
                project_job_id=project_job_id,
                project_cost_code_id=project_cost_code_id,
            )

    def enforce_budget(
        self,
        project_id: int,
        requested_amount: Decimal,
        *,
        project_job_id: int | None = None,
        project_cost_code_id: int | None = None,
        context_label: str | None = None,
        exclude_commitment_id: int | None = None,
    ) -> BudgetControlCheckDTO:
        check = self.check_budget(
            project_id,
            requested_amount,
            project_job_id=project_job_id,
            project_cost_code_id=project_cost_code_id,
            exclude_commitment_id=exclude_commitment_id,
        )
        if check.control_mode == "hard_stop" and check.would_exceed_budget:
            prefix = f"{context_label}: " if context_label else ""
            raise ValidationError(f"{prefix}{check.message}")
        return check

    def _resolve_budget_total(
        self,
        session: Session,
        *,
        version_id: int,
        version_total: Decimal,
        project_job_id: int | None,
        project_cost_code_id: int | None,
    ) -> Decimal:
        if project_job_id is None and project_cost_code_id is None:
            return self._to_money(version_total)
        return self._line_repository_factory(session).sum_by_version_dimension(
            version_id=version_id,
            project_job_id=project_job_id,
            project_cost_code_id=project_cost_code_id,
        )

    @staticmethod
    def _normalize_control_mode(control_mode: str | None) -> str:
        normalized = (control_mode or "none").strip().lower()
        return normalized if normalized in _CONTROL_MODES else "none"

    @staticmethod
    def _to_money(value: Decimal) -> Decimal:
        return Decimal(value).quantize(Decimal("0.01"))

    @staticmethod
    def _build_message(
        control_mode: str,
        would_exceed: bool,
        remaining_after: Decimal,
        *,
        no_budget: bool = False,
    ) -> str:
        if control_mode == "none":
            return "Budget control is disabled for this project."
        if no_budget:
            if control_mode == "hard_stop":
                return "Blocked: no approved budget exists for this project."
            return "Warning: no approved budget exists for this project."
        if not would_exceed:
            return "Within budget."
        overrun = abs(remaining_after)
        if control_mode == "warn":
            return f"Warning: this would exceed the approved budget by {overrun:,.2f}."
        return f"Blocked: this would exceed the approved budget by {overrun:,.2f}."
