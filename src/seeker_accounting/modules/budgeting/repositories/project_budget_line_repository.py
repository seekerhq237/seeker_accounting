from __future__ import annotations

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

    def add(self, line: ProjectBudgetLine) -> None:
        self._session.add(line)

    def save(self, line: ProjectBudgetLine) -> None:
        self._session.merge(line)

    def delete(self, line: ProjectBudgetLine) -> None:
        self._session.delete(line)
