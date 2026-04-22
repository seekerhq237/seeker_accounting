from __future__ import annotations

from sqlalchemy.orm import Session

from seeker_accounting.modules.contracts_projects.models.project_job import ProjectJob


class ProjectJobRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, job_id: int) -> ProjectJob | None:
        return self._session.get(ProjectJob, job_id)

    def get_by_project_and_job_code(self, project_id: int, job_code: str) -> ProjectJob | None:
        return (
            self._session.query(ProjectJob)
            .filter(ProjectJob.project_id == project_id, ProjectJob.job_code == job_code)
            .first()
        )

    def list_by_project(self, project_id: int) -> list[ProjectJob]:
        return (
            self._session.query(ProjectJob)
            .filter(ProjectJob.project_id == project_id)
            .order_by(ProjectJob.sequence_number, ProjectJob.job_code)
            .all()
        )

    def has_children(self, job_id: int) -> bool:
        return (
            self._session.query(ProjectJob)
            .filter(ProjectJob.parent_job_id == job_id)
            .first()
        ) is not None

    def add(self, job: ProjectJob) -> None:
        self._session.add(job)

    def save(self, job: ProjectJob) -> None:
        self._session.merge(job)
