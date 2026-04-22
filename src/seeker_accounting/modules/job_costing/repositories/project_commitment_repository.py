from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.job_costing.models.project_commitment import ProjectCommitment


class ProjectCommitmentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, commitment_id: int) -> ProjectCommitment | None:
        return self._session.get(ProjectCommitment, commitment_id)

    def get_by_company_and_id(self, company_id: int, commitment_id: int) -> ProjectCommitment | None:
        return self._session.scalar(
            select(ProjectCommitment).where(
                ProjectCommitment.company_id == company_id,
                ProjectCommitment.id == commitment_id,
            )
        )

    def get_by_company_and_number(self, company_id: int, commitment_number: str) -> ProjectCommitment | None:
        return self._session.scalar(
            select(ProjectCommitment).where(
                ProjectCommitment.company_id == company_id,
                ProjectCommitment.commitment_number == commitment_number,
            )
        )

    def list_by_project(self, project_id: int) -> list[ProjectCommitment]:
        return list(
            self._session.scalars(
                select(ProjectCommitment)
                .where(ProjectCommitment.project_id == project_id)
                .order_by(ProjectCommitment.commitment_number)
            )
        )

    def list_by_company(
        self, company_id: int, status_code: str | None = None
    ) -> list[ProjectCommitment]:
        stmt = select(ProjectCommitment).where(ProjectCommitment.company_id == company_id)
        if status_code is not None:
            stmt = stmt.where(ProjectCommitment.status_code == status_code)
        stmt = stmt.order_by(ProjectCommitment.commitment_number)
        return list(self._session.scalars(stmt))

    def sum_approved_total_by_project(self, project_id: int) -> Decimal:
        """Return the sum of total_amount for all approved (and partially_consumed) commitments."""
        result = self._session.scalar(
            select(func.coalesce(func.sum(ProjectCommitment.total_amount), 0)).where(
                ProjectCommitment.project_id == project_id,
                ProjectCommitment.status_code.in_(("approved", "partially_consumed")),
            )
        )
        return Decimal(str(result)) if result is not None else Decimal("0")

    def add(self, commitment: ProjectCommitment) -> None:
        self._session.add(commitment)

    def save(self, commitment: ProjectCommitment) -> None:
        self._session.merge(commitment)
