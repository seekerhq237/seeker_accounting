from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, utcnow

if TYPE_CHECKING:
    from seeker_accounting.modules.contracts_projects.models.contract import Contract
    from seeker_accounting.modules.contracts_projects.models.project import Project
    from seeker_accounting.modules.contracts_projects.models.project_cost_code import ProjectCostCode
    from seeker_accounting.modules.contracts_projects.models.project_job import ProjectJob
    from seeker_accounting.modules.payroll.models.payroll_run_employee import PayrollRunEmployee


class PayrollRunEmployeeProjectAllocation(Base):
    __tablename__ = "payroll_run_employee_project_allocations"
    __table_args__ = (
        UniqueConstraint("payroll_run_employee_id", "line_number"),
        Index("ix_payroll_run_employee_project_allocations_run_employee_id", "payroll_run_employee_id"),
        Index("ix_payroll_run_employee_project_allocations_project_job", "project_id", "project_job_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payroll_run_employee_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("payroll_run_employees.id", ondelete="CASCADE"),
        nullable=False,
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    contract_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("contracts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    project_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    project_job_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("project_jobs.id", ondelete="RESTRICT"),
        nullable=True,
    )
    project_cost_code_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("project_cost_codes.id", ondelete="RESTRICT"),
        nullable=True,
    )
    allocation_basis_code: Mapped[str] = mapped_column(String(20), nullable=False)
    allocation_quantity: Mapped[object | None] = mapped_column(Numeric(18, 4), nullable=True)
    allocation_percent: Mapped[object | None] = mapped_column(Numeric(9, 4), nullable=True)
    allocated_cost_amount: Mapped[object] = mapped_column(Numeric(18, 4), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)

    run_employee: Mapped["PayrollRunEmployee"] = relationship(
        "PayrollRunEmployee",
        back_populates="project_allocations",
    )
    contract: Mapped["Contract | None"] = relationship("Contract")
    project: Mapped["Project"] = relationship("Project")
    project_job: Mapped["ProjectJob | None"] = relationship("ProjectJob")
    project_cost_code: Mapped["ProjectCostCode | None"] = relationship("ProjectCostCode")