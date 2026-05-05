from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.budgeting.models.project_budget_line import ProjectBudgetLine


class ProjectBudgetLineRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, line_id: int) -> ProjectBudgetLine | None:
        return self._session.get(ProjectBudgetLine, line_id)

    def list_by_version(self, version_id: int) -> list[ProjectBudgetLine]:
        return (
            self._session.query(ProjectBudgetLine)
            .filter(ProjectBudgetLine.project_budget_version_id == version_id)
            .order_by(ProjectBudgetLine.line_number)
            .all()
        )

    def sum_by_version_dimension(
        self,
        version_id: int,
        project_job_id: int | None = None,
        project_cost_code_id: int | None = None,
    ) -> Decimal:
        statement = select(func.coalesce(func.sum(ProjectBudgetLine.line_amount), 0)).where(
            ProjectBudgetLine.project_budget_version_id == version_id,
        )
        if project_job_id is not None:
            statement = statement.where(ProjectBudgetLine.project_job_id == project_job_id)
        if project_cost_code_id is not None:
            statement = statement.where(ProjectBudgetLine.project_cost_code_id == project_cost_code_id)
        result = self._session.scalar(statement)
        return Decimal(str(result or 0)).quantize(Decimal("0.01"))

    def add(self, line: ProjectBudgetLine) -> None:
        self._session.add(line)

    def save(self, line: ProjectBudgetLine) -> None:
        self._session.merge(line)

    def delete(self, line: ProjectBudgetLine) -> None:
        self._session.delete(line)
