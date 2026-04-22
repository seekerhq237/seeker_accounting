from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.contracts_projects.models.contract_change_order import ContractChangeOrder
from seeker_accounting.modules.contracts_projects.models.project import Project


class ContractReportingRepository:
    """Read-only queries for contract-level management reporting.

    Provides project listing and change-order aggregation specific to reporting
    context.  Does not duplicate write-workflow logic from the operational repos.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_projects_by_contract(self, company_id: int, contract_id: int) -> list[Project]:
        """Return all projects linked to the given contract, scoped to company."""
        return list(
            self._session.scalars(
                select(Project)
                .where(
                    Project.company_id == company_id,
                    Project.contract_id == contract_id,
                )
                .order_by(Project.project_code.asc())
            )
        )

    def list_all_contracts_project_ids(self, company_id: int) -> dict[int, list[int]]:
        """Return a mapping of contract_id → [project_id, ...] for a company.

        Used when pre-loading project lists for all contracts in a single pass.
        """
        rows = self._session.execute(
            select(Project.contract_id, Project.id)
            .where(
                Project.company_id == company_id,
                Project.contract_id.is_not(None),
            )
            .order_by(Project.contract_id.asc(), Project.project_code.asc())
        ).all()
        result: dict[int, list[int]] = {}
        for row in rows:
            contract_id = row[0]
            project_id = row[1]
            result.setdefault(contract_id, []).append(project_id)
        return result

    def sum_approved_change_order_delta(self, contract_id: int) -> Decimal:
        """Sum all approved change order contract_amount_delta values for a contract."""
        raw = self._session.scalar(
            select(
                func.coalesce(
                    func.sum(ContractChangeOrder.contract_amount_delta),
                    0,
                )
            ).where(
                ContractChangeOrder.contract_id == contract_id,
                ContractChangeOrder.status_code == "approved",
            )
        )
        return Decimal(str(raw or 0)).quantize(Decimal("0.01"))
