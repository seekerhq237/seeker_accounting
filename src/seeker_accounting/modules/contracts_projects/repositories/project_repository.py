from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.contracts_projects.models.project import Project


class ProjectRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, project_id: int) -> Project | None:
        return self._session.get(Project, project_id)

    def get_by_company_and_id(self, company_id: int, project_id: int) -> Project | None:
        return self._session.scalar(
            select(Project).where(
                Project.company_id == company_id,
                Project.id == project_id,
            )
        )

    def get_by_company_and_project_code(self, company_id: int, project_code: str) -> Project | None:
        return self._session.scalar(
            select(Project).where(
                Project.company_id == company_id,
                Project.project_code == project_code,
            )
        )

    def list_by_company(self, company_id: int) -> list[Project]:
        return list(
            self._session.scalars(
                select(Project).where(Project.company_id == company_id).order_by(
                    Project.project_code.asc()
                )
            )
        )

    def add(self, project: Project) -> Project:
        self._session.add(project)
        return project

    def save(self, project: Project) -> Project:
        self._session.add(project)
        return project