from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.payroll.dto.payroll_calculation_dto import (
    CreatePayrollInputBatchCommand,
    CreatePayrollInputLineCommand,
    PayrollInputBatchDetailDTO,
    PayrollInputBatchListItemDTO,
    PayrollInputLineDTO,
    UpdatePayrollInputLineCommand,
)
from seeker_accounting.modules.payroll.models.payroll_input_batch import PayrollInputBatch
from seeker_accounting.modules.payroll.models.payroll_input_line import PayrollInputLine
from seeker_accounting.modules.payroll.repositories.employee_repository import EmployeeRepository
from seeker_accounting.modules.payroll.repositories.payroll_component_repository import (
    PayrollComponentRepository,
)
from seeker_accounting.modules.payroll.repositories.payroll_input_batch_repository import (
    PayrollInputBatchRepository,
    PayrollInputLineRepository,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError
from seeker_accounting.platform.numbering.numbering_service import NumberingService

PayrollInputBatchRepositoryFactory = Callable[[Session], PayrollInputBatchRepository]
PayrollInputLineRepositoryFactory = Callable[[Session], PayrollInputLineRepository]
EmployeeRepositoryFactory = Callable[[Session], EmployeeRepository]
PayrollComponentRepositoryFactory = Callable[[Session], PayrollComponentRepository]

_BATCH_DOC_TYPE = "payroll_input_batch"


class PayrollInputService:
    """Manage payroll variable input batches and their lines."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        batch_repository_factory: PayrollInputBatchRepositoryFactory,
        line_repository_factory: PayrollInputLineRepositoryFactory,
        employee_repository_factory: EmployeeRepositoryFactory,
        component_repository_factory: PayrollComponentRepositoryFactory,
        numbering_service: NumberingService,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._batch_repo_factory = batch_repository_factory
        self._line_repo_factory = line_repository_factory
        self._employee_repo_factory = employee_repository_factory
        self._component_repo_factory = component_repository_factory
        self._numbering_service = numbering_service

    # ── Batch queries ─────────────────────────────────────────────────────────

    def list_batches(
        self,
        company_id: int,
        period_year: int | None = None,
        period_month: int | None = None,
        status_code: str | None = None,
    ) -> list[PayrollInputBatchListItemDTO]:
        with self._uow_factory() as uow:
            repo = self._batch_repo_factory(uow.session)
            batches = repo.list_by_company(
                company_id,
                period_year=period_year,
                period_month=period_month,
                status_code=status_code,
            )
            return [self._to_batch_list_dto(b) for b in batches]

    def get_batch(self, company_id: int, batch_id: int) -> PayrollInputBatchDetailDTO:
        with self._uow_factory() as uow:
            repo = self._batch_repo_factory(uow.session)
            batch = repo.get_by_id(company_id, batch_id)
            if batch is None:
                raise NotFoundError("Payroll input batch not found.")
            return self._to_batch_detail_dto(batch)

    # ── Batch commands ────────────────────────────────────────────────────────

    def create_batch(
        self, company_id: int, cmd: CreatePayrollInputBatchCommand
    ) -> PayrollInputBatchDetailDTO:
        self._validate_period(cmd.period_year, cmd.period_month)
        with self._uow_factory() as uow:
            ref = self._numbering_service.issue_next_number(
                uow.session, company_id, _BATCH_DOC_TYPE
            )
            batch = PayrollInputBatch(
                company_id=company_id,
                batch_reference=ref,
                period_year=cmd.period_year,
                period_month=cmd.period_month,
                status_code="draft",
                description=cmd.description,
            )
            repo = self._batch_repo_factory(uow.session)
            repo.save(batch)
            uow.commit()
            uow.session.refresh(batch)
            return self._to_batch_detail_dto(batch)

    def submit_batch(self, company_id: int, batch_id: int) -> None:
        with self._uow_factory() as uow:
            repo = self._batch_repo_factory(uow.session)
            batch = repo.get_by_id(company_id, batch_id)
            if batch is None:
                raise NotFoundError("Payroll input batch not found.")
            if batch.status_code != "draft":
                raise ValidationError("Only draft batches can be submitted.")
            batch.status_code = "approved"
            batch.submitted_at = datetime.now(timezone.utc)
            batch.approved_at = datetime.now(timezone.utc)
            uow.commit()

    def void_batch(self, company_id: int, batch_id: int) -> None:
        with self._uow_factory() as uow:
            repo = self._batch_repo_factory(uow.session)
            batch = repo.get_by_id(company_id, batch_id)
            if batch is None:
                raise NotFoundError("Payroll input batch not found.")
            if batch.status_code == "voided":
                raise ValidationError("Batch is already voided.")
            batch.status_code = "voided"
            uow.commit()

    # ── Line commands ─────────────────────────────────────────────────────────

    def add_line(
        self, company_id: int, batch_id: int, cmd: CreatePayrollInputLineCommand
    ) -> PayrollInputLineDTO:
        with self._uow_factory() as uow:
            batch_repo = self._batch_repo_factory(uow.session)
            batch = batch_repo.get_by_id(company_id, batch_id)
            if batch is None:
                raise NotFoundError("Payroll input batch not found.")
            if batch.status_code != "draft":
                raise ValidationError("Lines can only be added to draft batches.")

            emp_repo = self._employee_repo_factory(uow.session)
            employee = emp_repo.get_by_id(company_id, cmd.employee_id)
            if employee is None:
                raise NotFoundError("Employee not found.")

            comp_repo = self._component_repo_factory(uow.session)
            comp = comp_repo.get_by_id(company_id, cmd.component_id)
            if comp is None:
                raise NotFoundError("Payroll component not found.")

            if cmd.input_amount <= Decimal("0"):
                raise ValidationError("Input amount must be greater than zero.")

            line = PayrollInputLine(
                company_id=company_id,
                batch_id=batch_id,
                employee_id=cmd.employee_id,
                component_id=cmd.component_id,
                input_amount=cmd.input_amount,
                input_quantity=cmd.input_quantity,
                notes=cmd.notes,
            )
            line_repo = self._line_repo_factory(uow.session)
            line_repo.save(line)
            uow.commit()
            uow.session.refresh(line)
            return self._to_line_dto(line)

    def update_line(
        self,
        company_id: int,
        batch_id: int,
        line_id: int,
        cmd: UpdatePayrollInputLineCommand,
    ) -> PayrollInputLineDTO:
        with self._uow_factory() as uow:
            batch_repo = self._batch_repo_factory(uow.session)
            batch = batch_repo.get_by_id(company_id, batch_id)
            if batch is None:
                raise NotFoundError("Payroll input batch not found.")
            if batch.status_code != "draft":
                raise ValidationError("Lines can only be edited in draft batches.")

            line_repo = self._line_repo_factory(uow.session)
            line = line_repo.get_by_id(company_id, line_id)
            if line is None or line.batch_id != batch_id:
                raise NotFoundError("Input line not found.")

            if cmd.input_amount <= Decimal("0"):
                raise ValidationError("Input amount must be greater than zero.")

            line.input_amount = cmd.input_amount
            line.input_quantity = cmd.input_quantity
            line.notes = cmd.notes

            uow.commit()
            uow.session.refresh(line)
            return self._to_line_dto(line)

    def delete_line(self, company_id: int, batch_id: int, line_id: int) -> None:
        with self._uow_factory() as uow:
            batch_repo = self._batch_repo_factory(uow.session)
            batch = batch_repo.get_by_id(company_id, batch_id)
            if batch is None:
                raise NotFoundError("Payroll input batch not found.")
            if batch.status_code != "draft":
                raise ValidationError("Lines can only be deleted from draft batches.")

            line_repo = self._line_repo_factory(uow.session)
            line = line_repo.get_by_id(company_id, line_id)
            if line is None or line.batch_id != batch_id:
                raise NotFoundError("Input line not found.")
            line_repo.delete(line)
            uow.commit()

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _validate_period(year: int, month: int) -> None:
        if not (2000 <= year <= 2100):
            raise ValidationError("Period year must be between 2000 and 2100.")
        if not (1 <= month <= 12):
            raise ValidationError("Period month must be between 1 and 12.")

    @staticmethod
    def _to_batch_list_dto(b: PayrollInputBatch) -> PayrollInputBatchListItemDTO:
        return PayrollInputBatchListItemDTO(
            id=b.id,
            company_id=b.company_id,
            batch_reference=b.batch_reference,
            period_year=b.period_year,
            period_month=b.period_month,
            status_code=b.status_code,
            description=b.description,
            line_count=len(b.lines) if b.lines else 0,
        )

    @staticmethod
    def _to_batch_detail_dto(b: PayrollInputBatch) -> PayrollInputBatchDetailDTO:
        return PayrollInputBatchDetailDTO(
            id=b.id,
            company_id=b.company_id,
            batch_reference=b.batch_reference,
            period_year=b.period_year,
            period_month=b.period_month,
            status_code=b.status_code,
            description=b.description,
            submitted_at=b.submitted_at,
            approved_at=b.approved_at,
            lines=[PayrollInputService._to_line_dto(l) for l in (b.lines or [])],
        )

    @staticmethod
    def _to_line_dto(l: PayrollInputLine) -> PayrollInputLineDTO:
        from decimal import Decimal
        return PayrollInputLineDTO(
            id=l.id,
            batch_id=l.batch_id,
            employee_id=l.employee_id,
            employee_display_name=l.employee.display_name if l.employee else "",
            component_id=l.component_id,
            component_name=l.component.component_name if l.component else "",
            component_type_code=l.component.component_type_code if l.component else "",
            input_amount=Decimal(str(l.input_amount)),
            input_quantity=Decimal(str(l.input_quantity)) if l.input_quantity is not None else None,
            notes=l.notes,
        )
