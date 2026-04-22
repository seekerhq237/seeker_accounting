from __future__ import annotations

from sqlalchemy.orm import Session

from seeker_accounting.modules.contracts_projects.models.project_cost_code import ProjectCostCode


class ProjectCostCodeRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, cost_code_id: int) -> ProjectCostCode | None:
        return self._session.get(ProjectCostCode, cost_code_id)

    def get_by_company_and_code(self, company_id: int, code: str) -> ProjectCostCode | None:
        return (
            self._session.query(ProjectCostCode)
            .filter(ProjectCostCode.company_id == company_id, ProjectCostCode.code == code)
            .first()
        )

    def list_by_company(self, company_id: int, active_only: bool = False) -> list[ProjectCostCode]:
        query = self._session.query(ProjectCostCode).filter(
            ProjectCostCode.company_id == company_id
        )
        if active_only:
            query = query.filter(ProjectCostCode.is_active.is_(True))
        return query.order_by(ProjectCostCode.code).all()

    def add(self, cost_code: ProjectCostCode) -> None:
        self._session.add(cost_code)

    def save(self, cost_code: ProjectCostCode) -> None:
        self._session.merge(cost_code)
