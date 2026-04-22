from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.budgeting.models.project_budget_line import ProjectBudgetLine
from seeker_accounting.modules.budgeting.models.project_budget_version import ProjectBudgetVersion
from seeker_accounting.modules.contracts_projects.models.project_cost_code import ProjectCostCode
from seeker_accounting.modules.contracts_projects.models.project_job import ProjectJob
from seeker_accounting.modules.job_costing.models.project_commitment import ProjectCommitment
from seeker_accounting.modules.job_costing.models.project_commitment_line import ProjectCommitmentLine
from seeker_accounting.modules.sales.models.sales_invoice import SalesInvoice
from seeker_accounting.modules.sales.models.sales_invoice_line import SalesInvoiceLine


@dataclass(frozen=True, slots=True)
class ProjectDimensionAmountRow:
    project_job_id: int | None
    project_job_code: str | None
    project_job_name: str | None
    project_cost_code_id: int | None
    project_cost_code: str | None
    project_cost_code_name: str | None
    amount: Decimal


class ProjectProfitabilityQueryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_revenue_by_dimension(
        self,
        company_id: int,
        project_id: int,
    ) -> list[ProjectDimensionAmountRow]:
        resolved_project_id = func.coalesce(SalesInvoiceLine.project_id, SalesInvoice.project_id)
        statement = (
            select(
                SalesInvoiceLine.project_job_id.label("project_job_id"),
                ProjectJob.job_code.label("project_job_code"),
                ProjectJob.job_name.label("project_job_name"),
                SalesInvoiceLine.project_cost_code_id.label("project_cost_code_id"),
                ProjectCostCode.code.label("project_cost_code"),
                ProjectCostCode.name.label("project_cost_code_name"),
                func.coalesce(func.sum(SalesInvoiceLine.line_subtotal_amount), 0).label("amount"),
            )
            .join(SalesInvoice, SalesInvoice.id == SalesInvoiceLine.sales_invoice_id)
            .outerjoin(ProjectJob, ProjectJob.id == SalesInvoiceLine.project_job_id)
            .outerjoin(ProjectCostCode, ProjectCostCode.id == SalesInvoiceLine.project_cost_code_id)
            .where(
                SalesInvoice.company_id == company_id,
                SalesInvoice.status_code == "posted",
                SalesInvoice.posted_at.is_not(None),
                resolved_project_id == project_id,
            )
            .group_by(
                SalesInvoiceLine.project_job_id,
                ProjectJob.job_code,
                ProjectJob.job_name,
                SalesInvoiceLine.project_cost_code_id,
                ProjectCostCode.code,
                ProjectCostCode.name,
            )
        )
        return self._build_dimension_rows(statement)

    def list_current_budget_by_dimension(self, project_id: int) -> list[ProjectDimensionAmountRow]:
        version_id = self._session.scalar(
            select(ProjectBudgetVersion.id)
            .where(
                ProjectBudgetVersion.project_id == project_id,
                ProjectBudgetVersion.status_code == "approved",
            )
            .order_by(desc(ProjectBudgetVersion.version_number))
            .limit(1)
        )
        if version_id is None:
            return []

        statement = (
            select(
                ProjectBudgetLine.project_job_id.label("project_job_id"),
                ProjectJob.job_code.label("project_job_code"),
                ProjectJob.job_name.label("project_job_name"),
                ProjectBudgetLine.project_cost_code_id.label("project_cost_code_id"),
                ProjectCostCode.code.label("project_cost_code"),
                ProjectCostCode.name.label("project_cost_code_name"),
                func.coalesce(func.sum(ProjectBudgetLine.line_amount), 0).label("amount"),
            )
            .outerjoin(ProjectJob, ProjectJob.id == ProjectBudgetLine.project_job_id)
            .outerjoin(ProjectCostCode, ProjectCostCode.id == ProjectBudgetLine.project_cost_code_id)
            .where(ProjectBudgetLine.project_budget_version_id == version_id)
            .group_by(
                ProjectBudgetLine.project_job_id,
                ProjectJob.job_code,
                ProjectJob.job_name,
                ProjectBudgetLine.project_cost_code_id,
                ProjectCostCode.code,
                ProjectCostCode.name,
            )
        )
        return self._build_dimension_rows(statement)

    def list_open_commitments_by_dimension(self, project_id: int) -> list[ProjectDimensionAmountRow]:
        statement = (
            select(
                ProjectCommitmentLine.project_job_id.label("project_job_id"),
                ProjectJob.job_code.label("project_job_code"),
                ProjectJob.job_name.label("project_job_name"),
                ProjectCommitmentLine.project_cost_code_id.label("project_cost_code_id"),
                ProjectCostCode.code.label("project_cost_code"),
                ProjectCostCode.name.label("project_cost_code_name"),
                func.coalesce(func.sum(ProjectCommitmentLine.line_amount), 0).label("amount"),
            )
            .join(ProjectCommitment, ProjectCommitment.id == ProjectCommitmentLine.project_commitment_id)
            .outerjoin(ProjectJob, ProjectJob.id == ProjectCommitmentLine.project_job_id)
            .outerjoin(ProjectCostCode, ProjectCostCode.id == ProjectCommitmentLine.project_cost_code_id)
            .where(
                ProjectCommitment.project_id == project_id,
                ProjectCommitment.status_code == "approved",
            )
            .group_by(
                ProjectCommitmentLine.project_job_id,
                ProjectJob.job_code,
                ProjectJob.job_name,
                ProjectCommitmentLine.project_cost_code_id,
                ProjectCostCode.code,
                ProjectCostCode.name,
            )
        )
        return self._build_dimension_rows(statement)

    def _build_dimension_rows(self, statement) -> list[ProjectDimensionAmountRow]:
        result: list[ProjectDimensionAmountRow] = []
        for row in self._session.execute(statement):
            amount = self._to_decimal(row.amount)
            if amount == Decimal("0.00"):
                continue
            result.append(
                ProjectDimensionAmountRow(
                    project_job_id=row.project_job_id,
                    project_job_code=row.project_job_code,
                    project_job_name=row.project_job_name,
                    project_cost_code_id=row.project_cost_code_id,
                    project_cost_code=row.project_cost_code,
                    project_cost_code_name=row.project_cost_code_name,
                    amount=amount,
                )
            )
        return sorted(
            result,
            key=lambda item: (
                item.project_job_code or "",
                item.project_cost_code or "",
            ),
        )

    @staticmethod
    def _to_decimal(value: object) -> Decimal:
        if isinstance(value, Decimal):
            return value.quantize(Decimal("0.01"))
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))