from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.job_costing.models.project_commitment_line import ProjectCommitmentLine


class ProjectCommitmentLineRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, line_id: int) -> ProjectCommitmentLine | None:
        return self._session.get(ProjectCommitmentLine, line_id)

    def list_by_commitment(self, commitment_id: int) -> list[ProjectCommitmentLine]:
        return list(
            self._session.scalars(
                select(ProjectCommitmentLine)
                .where(ProjectCommitmentLine.project_commitment_id == commitment_id)
                .order_by(ProjectCommitmentLine.line_number)
            )
        )

    def add(self, line: ProjectCommitmentLine) -> None:
        self._session.add(line)

    def save(self, line: ProjectCommitmentLine) -> None:
        self._session.merge(line)

    def delete(self, line: ProjectCommitmentLine) -> None:
        self._session.delete(line)
