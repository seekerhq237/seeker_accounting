"""PayrollPaymentTrackingService — internal employee net-pay settlement tracking.

Responsibilities:
  - Create / update / delete payment records for payroll_run_employees
  - Compute and update payment_status_code on the employee row from cumulative records
  - Prevent recording payments against unposted runs
  - Expose EmployeePaymentSummaryDTO for UI
  - Does NOT execute disbursements or call any external payment systems
"""

from __future__ import annotations

import json
from datetime import date, timezone
from decimal import Decimal
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.audit.dto.audit_event_dto import RecordAuditEventCommand
from seeker_accounting.modules.audit.services.audit_service import AuditService
from seeker_accounting.modules.payroll.dto.payroll_payment_dto import (
    CreatePayrollPaymentRecordCommand,
    EmployeePaymentSummaryDTO,
    PayrollPaymentRecordDTO,
    UpdatePayrollPaymentRecordCommand,
    _ALLOWED_PAYMENT_METHODS,
)
from seeker_accounting.modules.payroll.payroll_permissions import PAYROLL_PAYMENT_MANAGE
from seeker_accounting.modules.payroll.models.payroll_payment_record import (
    PayrollPaymentRecord,
)
from seeker_accounting.modules.payroll.models.payroll_run import PayrollRun
from seeker_accounting.modules.payroll.models.payroll_run_employee import PayrollRunEmployee
from seeker_accounting.modules.payroll.repositories.payroll_payment_record_repository import (
    PayrollPaymentRecordRepository,
)
from seeker_accounting.modules.payroll.repositories.payroll_run_repository import (
    PayrollRunEmployeeRepository,
    PayrollRunRepository,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

_TOLERANCE = Decimal("0.005")


class PayrollPaymentTrackingService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        run_repository_factory: Callable[[Session], PayrollRunRepository],
        run_employee_repository_factory: Callable[[Session], PayrollRunEmployeeRepository],
        payment_record_repository_factory: Callable[
            [Session], PayrollPaymentRecordRepository
        ],
        permission_service: PermissionService,
        audit_service: AuditService,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._run_repo_factory = run_repository_factory
        self._run_emp_repo_factory = run_employee_repository_factory
        self._payment_repo_factory = payment_record_repository_factory
        self._permission_service = permission_service
        self._audit_service = audit_service

    # ── Queries ───────────────────────────────────────────────────────────────

    def get_employee_payment_summary(
        self, company_id: int, run_employee_id: int
    ) -> EmployeePaymentSummaryDTO:
        self._permission_service.require_permission(PAYROLL_PAYMENT_MANAGE)
        with self._uow_factory() as uow:
            emp_repo = self._run_emp_repo_factory(uow.session)
            emp = emp_repo.get_by_id(company_id, run_employee_id)
            if emp is None:
                raise NotFoundError("Employee payroll detail not found.")
            run = self._run_repo_factory(uow.session).get_by_id(company_id, emp.run_id)
            pay_repo = self._payment_repo_factory(uow.session)
            records = pay_repo.list_by_run_employee(company_id, run_employee_id)
            return self._build_summary(emp, run, records)

    def list_run_payment_summaries(
        self, company_id: int, run_id: int
    ) -> list[EmployeePaymentSummaryDTO]:
        self._permission_service.require_permission(PAYROLL_PAYMENT_MANAGE)
        with self._uow_factory() as uow:
            run = self._run_repo_factory(uow.session).get_by_id(company_id, run_id)
            if run is None:
                raise NotFoundError("Payroll run not found.")
            emp_repo = self._run_emp_repo_factory(uow.session)
            employees = emp_repo.list_by_run(company_id, run_id)
            pay_repo = self._payment_repo_factory(uow.session)
            result = []
            for emp in employees:
                if emp.status_code != "included":
                    continue
                records = pay_repo.list_by_run_employee(company_id, emp.id)
                result.append(self._build_summary(emp, run, records))
            return result

    # ── Commands ──────────────────────────────────────────────────────────────

    def create_payment_record(
        self,
        company_id: int,
        cmd: CreatePayrollPaymentRecordCommand,
        actor_user_id: int | None = None,
    ) -> EmployeePaymentSummaryDTO:
        self._permission_service.require_permission(PAYROLL_PAYMENT_MANAGE)
        self._validate_method(cmd.payment_method_code)
        self._validate_amount(cmd.amount_paid, "amount_paid")

        with self._uow_factory() as uow:
            emp = self._require_included_employee(uow.session, company_id, cmd.run_employee_id)
            run = self._require_posted_run(uow.session, company_id, emp.run_id)

            record = PayrollPaymentRecord(
                company_id=company_id,
                run_employee_id=emp.id,
                payment_date=cmd.payment_date,
                amount_paid=cmd.amount_paid,
                payment_method_code=cmd.payment_method_code,
                payment_reference=cmd.payment_reference,
                treasury_transaction_id=cmd.treasury_transaction_id,
                notes=cmd.notes,
                created_by_user_id=actor_user_id,
                updated_by_user_id=actor_user_id,
            )
            pay_repo = self._payment_repo_factory(uow.session)
            existing_records = pay_repo.list_by_run_employee(company_id, emp.id)
            self._validate_total_paid(emp, existing_records, cmd.amount_paid)
            pay_repo.save(record)
            uow.session.flush()

            # Recompute and save payment status
            records = pay_repo.list_by_run_employee(company_id, emp.id)
            self._update_payment_status(emp, records)
            self._audit_service.record_event_in_session(
                uow.session,
                company_id,
                RecordAuditEventCommand(
                    event_type_code="PAYROLL_PAYMENT_CREATED",
                    module_code="payroll",
                    entity_type="payroll_payment_record",
                    entity_id=record.id,
                    description=(
                        f"Created payroll payment record for employee detail {emp.id}."
                    ),
                    detail_json=json.dumps(
                        {
                            "run_employee_id": emp.id,
                            "amount_paid": str(cmd.amount_paid),
                            "payment_method_code": cmd.payment_method_code,
                            "payment_date": cmd.payment_date.isoformat(),
                        }
                    ),
                ),
            )
            uow.commit()

            return self._build_summary(emp, run, records)

    def update_payment_record(
        self,
        company_id: int,
        record_id: int,
        cmd: UpdatePayrollPaymentRecordCommand,
        actor_user_id: int | None = None,
    ) -> EmployeePaymentSummaryDTO:
        self._permission_service.require_permission(PAYROLL_PAYMENT_MANAGE)
        self._validate_method(cmd.payment_method_code)
        self._validate_amount(cmd.amount_paid, "amount_paid")

        with self._uow_factory() as uow:
            pay_repo = self._payment_repo_factory(uow.session)
            record = pay_repo.get_by_id(company_id, record_id)
            if record is None:
                raise NotFoundError("Payment record not found.")
            emp = self._require_included_employee(
                uow.session, company_id, record.run_employee_id
            )
            run = self._require_posted_run(uow.session, company_id, emp.run_id)
            existing_records = [
                item
                for item in pay_repo.list_by_run_employee(company_id, emp.id)
                if item.id != record.id
            ]
            self._validate_total_paid(emp, existing_records, cmd.amount_paid)

            record.payment_date = cmd.payment_date
            record.amount_paid = cmd.amount_paid
            record.payment_method_code = cmd.payment_method_code
            record.payment_reference = cmd.payment_reference
            record.treasury_transaction_id = cmd.treasury_transaction_id
            record.notes = cmd.notes
            record.updated_by_user_id = actor_user_id
            pay_repo.save(record)
            uow.session.flush()

            records = pay_repo.list_by_run_employee(company_id, emp.id)
            self._update_payment_status(emp, records)
            self._audit_service.record_event_in_session(
                uow.session,
                company_id,
                RecordAuditEventCommand(
                    event_type_code="PAYROLL_PAYMENT_UPDATED",
                    module_code="payroll",
                    entity_type="payroll_payment_record",
                    entity_id=record.id,
                    description=f"Updated payroll payment record {record.id}.",
                    detail_json=json.dumps(
                        {
                            "run_employee_id": emp.id,
                            "amount_paid": str(cmd.amount_paid),
                            "payment_method_code": cmd.payment_method_code,
                            "payment_date": cmd.payment_date.isoformat(),
                        }
                    ),
                ),
            )
            uow.commit()
            return self._build_summary(emp, run, records)

    def delete_payment_record(
        self, company_id: int, record_id: int
    ) -> None:
        self._permission_service.require_permission(PAYROLL_PAYMENT_MANAGE)
        with self._uow_factory() as uow:
            pay_repo = self._payment_repo_factory(uow.session)
            record = pay_repo.get_by_id(company_id, record_id)
            if record is None:
                raise NotFoundError("Payment record not found.")
            emp = self._require_included_employee(
                uow.session, company_id, record.run_employee_id
            )
            self._require_posted_run(uow.session, company_id, emp.run_id)

            pay_repo.delete(record)
            uow.session.flush()

            remaining = pay_repo.list_by_run_employee(company_id, emp.id)
            self._update_payment_status(emp, remaining)
            self._audit_service.record_event_in_session(
                uow.session,
                company_id,
                RecordAuditEventCommand(
                    event_type_code="PAYROLL_PAYMENT_DELETED",
                    module_code="payroll",
                    entity_type="payroll_payment_record",
                    entity_id=record_id,
                    description=f"Deleted payroll payment record {record_id}.",
                    detail_json=json.dumps(
                        {
                            "run_employee_id": emp.id,
                            "remaining_record_count": len(remaining),
                        }
                    ),
                ),
            )
            uow.commit()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _require_included_employee(
        self, session: Session, company_id: int, run_employee_id: int
    ) -> PayrollRunEmployee:
        emp_repo = self._run_emp_repo_factory(session)
        emp = emp_repo.get_by_id(company_id, run_employee_id)
        if emp is None:
            raise NotFoundError("Employee payroll detail not found.")
        if emp.status_code != "included":
            raise ValidationError(
                "Payment tracking is only supported for included employees."
            )
        return emp

    def _require_posted_run(
        self, session: Session, company_id: int, run_id: int
    ) -> PayrollRun:
        run = self._run_repo_factory(session).get_by_id(company_id, run_id)
        if run is None:
            raise NotFoundError("Payroll run not found.")
        if run.status_code != "posted":
            raise ValidationError(
                "Payment tracking can only be applied to posted payroll runs."
            )
        return run

    @staticmethod
    def _update_payment_status(
        emp: PayrollRunEmployee, records: list[PayrollPaymentRecord]
    ) -> None:
        total_paid = sum(
            (Decimal(str(r.amount_paid)) for r in records), Decimal("0")
        )
        net = Decimal(str(emp.net_payable))
        if total_paid <= _TOLERANCE:
            emp.payment_status_code = "unpaid"
            emp.payment_date = None
        elif total_paid >= net - _TOLERANCE:
            emp.payment_status_code = "paid"
            emp.payment_date = max(r.payment_date for r in records) if records else None
        else:
            emp.payment_status_code = "partial"
            emp.payment_date = None

    @staticmethod
    def _validate_method(code: str | None) -> None:
        if code is not None and code not in _ALLOWED_PAYMENT_METHODS:
            raise ValidationError(
                f"Invalid payment method '{code}'. "
                f"Allowed: {', '.join(sorted(_ALLOWED_PAYMENT_METHODS))}"
            )

    @staticmethod
    def _validate_amount(amount: Decimal, label: str) -> None:
        if amount <= Decimal("0"):
            raise ValidationError(f"{label} must be greater than zero.")

    @staticmethod
    def _validate_total_paid(
        emp: PayrollRunEmployee,
        records: list[PayrollPaymentRecord],
        next_amount: Decimal,
    ) -> None:
        total_paid = sum((Decimal(str(r.amount_paid)) for r in records), Decimal("0"))
        proposed_total = total_paid + next_amount
        net = Decimal(str(emp.net_payable))
        if proposed_total > net + _TOLERANCE:
            raise ValidationError(
                "Payment amount exceeds employee net payable beyond tolerance. "
                f"Net payable={net:.4f}, proposed total paid={proposed_total:.4f}."
            )

    @staticmethod
    def _build_summary(
        emp: PayrollRunEmployee,
        run: PayrollRun | None,
        records: list[PayrollPaymentRecord],
    ) -> EmployeePaymentSummaryDTO:
        employee = emp.employee
        net = Decimal(str(emp.net_payable))
        total_paid = sum(
            (Decimal(str(r.amount_paid)) for r in records), Decimal("0")
        )
        rec_dtos = tuple(
            PayrollPaymentRecordDTO(
                id=r.id,
                company_id=r.company_id,
                run_employee_id=r.run_employee_id,
                payment_date=r.payment_date,
                amount_paid=Decimal(str(r.amount_paid)),
                payment_method_code=r.payment_method_code,
                payment_reference=r.payment_reference,
                treasury_transaction_id=r.treasury_transaction_id,
                notes=r.notes,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
            for r in records
        )
        return EmployeePaymentSummaryDTO(
            run_employee_id=emp.id,
            run_id=emp.run_id,
            run_reference=run.run_reference if run else "",
            employee_id=emp.employee_id,
            employee_number=employee.employee_number if employee else "",
            employee_display_name=employee.display_name if employee else "",
            net_payable=net,
            total_paid=total_paid,
            outstanding=max(net - total_paid, Decimal("0")),
            payment_status_code=emp.payment_status_code,
            payment_date=emp.payment_date,
            records=rec_dtos,
        )
