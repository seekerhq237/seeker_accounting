from __future__ import annotations

from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.budgeting.dto.budget_control_dto import BudgetControlCheckDTO
from seeker_accounting.modules.budgeting.repositories.project_budget_version_repository import (
    ProjectBudgetVersionRepository,
)
from seeker_accounting.modules.contracts_projects.repositories.project_repository import ProjectRepository
from seeker_accounting.platform.exceptions import NotFoundError

ProjectBudgetVersionRepositoryFactory = Callable[[Session], ProjectBudgetVersionRepository]
ProjectRepositoryFactory = Callable[[Session], ProjectRepository]

_ZERO = Decimal("0")


class BudgetControlService:
    """Check budget availability for a project against the current approved budget.

    Commitments and actuals are placeholders (zero) until those subsystems exist.
    """

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        version_repository_factory: ProjectBudgetVersionRepositoryFactory,
        project_repository_factory: ProjectRepositoryFactory,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._version_repository_factory = version_repository_factory
        self._project_repository_factory = project_repository_factory

    def check_budget(self, project_id: int, requested_amount: Decimal) -> BudgetControlCheckDTO:
        """Return a budget control check result for the requested amount against
        the current approved budget for *project_id*.

        If the project has no approved budget or control mode is ``"none"`` (or unset),
        the check always passes.
        """
        with self._unit_of_work_factory() as uow:
            project_repo = self._project_repository_factory(uow.session)
            project = project_repo.get_by_id(project_id)
            if project is None:
                raise NotFoundError(f"Project {project_id} not found.")

            control_mode = project.budget_control_mode_code or "none"

            version_repo = self._version_repository_factory(uow.session)
            approved = version_repo.get_current_approved(project_id)

            if approved is None:
                return BudgetControlCheckDTO(
                    project_id=project_id,
                    budget_version_id=None,
                    budget_total=_ZERO,
                    control_mode=control_mode,
                    requested_amount=requested_amount,
                    committed_amount=_ZERO,
                    actual_amount=_ZERO,
                    remaining_before_request=_ZERO,
                    remaining_after_request=_ZERO - requested_amount,
                    would_exceed_budget=False,
                    message="No approved budget exists for this project.",
                )

            budget_total = approved.total_budget_amount
            committed = _ZERO  # placeholder until commitment tracking exists
            actual = _ZERO  # placeholder until actual cost integration exists
            consumed = committed + actual
            remaining_before = budget_total - consumed
            remaining_after = remaining_before - requested_amount
            would_exceed = remaining_after < _ZERO

            if control_mode == "none":
                message = "Budget control is disabled for this project."
            elif not would_exceed:
                message = "Within budget."
            elif control_mode == "warn":
                message = (
                    f"Warning: This would exceed the approved budget by "
                    f"{abs(remaining_after):,.2f}."
                )
            else:  # hard_stop
                message = (
                    f"Blocked: This would exceed the approved budget by "
                    f"{abs(remaining_after):,.2f}. Budget control mode is hard stop."
                )

            return BudgetControlCheckDTO(
                project_id=project_id,
                budget_version_id=approved.id,
                budget_total=budget_total,
                control_mode=control_mode,
                requested_amount=requested_amount,
                committed_amount=committed,
                actual_amount=actual,
                remaining_before_request=remaining_before,
                remaining_after_request=remaining_after,
                would_exceed_budget=would_exceed and control_mode != "none",
                message=message,
            )
