from __future__ import annotations

from sqlalchemy.orm import Session

from seeker_accounting.modules.budgeting.models.project_budget_version import ProjectBudgetVersion


class ProjectBudgetVersionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, version_id: int) -> ProjectBudgetVersion | None:
        return self._session.get(ProjectBudgetVersion, version_id)

    def get_by_company_and_id(self, company_id: int, version_id: int) -> ProjectBudgetVersion | None:
        return (
            self._session.query(ProjectBudgetVersion)
            .filter(
                ProjectBudgetVersion.company_id == company_id,
                ProjectBudgetVersion.id == version_id,
            )
            .first()
        )

    def get_by_project_and_version_number(
        self, project_id: int, version_number: int
    ) -> ProjectBudgetVersion | None:
        return (
            self._session.query(ProjectBudgetVersion)
            .filter(
                ProjectBudgetVersion.project_id == project_id,
                ProjectBudgetVersion.version_number == version_number,
            )
            .first()
        )

    def list_by_project(self, project_id: int) -> list[ProjectBudgetVersion]:
        return (
            self._session.query(ProjectBudgetVersion)
            .filter(ProjectBudgetVersion.project_id == project_id)
            .order_by(ProjectBudgetVersion.version_number)
            .all()
        )

    def get_current_approved(self, project_id: int) -> ProjectBudgetVersion | None:
        """Return the single approved (non-superseded, non-cancelled) version for a project."""
        return (
            self._session.query(ProjectBudgetVersion)
            .filter(
                ProjectBudgetVersion.project_id == project_id,
                ProjectBudgetVersion.status_code == "approved",
            )
            .first()
        )

    def get_max_version_number(self, project_id: int) -> int:
        from sqlalchemy import func

        result = (
            self._session.query(func.max(ProjectBudgetVersion.version_number))
            .filter(ProjectBudgetVersion.project_id == project_id)
            .scalar()
        )
        return result or 0

    def add(self, version: ProjectBudgetVersion) -> None:
        self._session.add(version)

    def save(self, version: ProjectBudgetVersion) -> None:
        self._session.merge(version)
