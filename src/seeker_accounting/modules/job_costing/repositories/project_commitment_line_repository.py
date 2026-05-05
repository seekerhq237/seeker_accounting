from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.job_costing.models.project_commitment import ProjectCommitment
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

    def sum_open_by_project_dimension(
        self,
        project_id: int,
        project_job_id: int | None = None,
        project_cost_code_id: int | None = None,
        exclude_commitment_id: int | None = None,
    ) -> Decimal:
        statement = (
            select(func.coalesce(func.sum(ProjectCommitmentLine.line_amount), 0))
            .join(ProjectCommitment, ProjectCommitment.id == ProjectCommitmentLine.project_commitment_id)
            .where(
                ProjectCommitment.project_id == project_id,
                ProjectCommitment.status_code.in_(("approved", "partially_consumed")),
            )
        )
        if project_job_id is not None:
            statement = statement.where(ProjectCommitmentLine.project_job_id == project_job_id)
        if project_cost_code_id is not None:
            statement = statement.where(ProjectCommitmentLine.project_cost_code_id == project_cost_code_id)
        if exclude_commitment_id is not None:
            statement = statement.where(ProjectCommitment.id != exclude_commitment_id)
        result = self._session.scalar(statement)
        return Decimal(str(result or 0)).quantize(Decimal("0.01"))

    def add(self, line: ProjectCommitmentLine) -> None:
        self._session.add(line)

    def save(self, line: ProjectCommitmentLine) -> None:
        self._session.merge(line)

    def delete(self, line: ProjectCommitmentLine) -> None:
        self._session.delete(line)
