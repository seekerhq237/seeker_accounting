"""PayrollRemittanceService — statutory remittance batch tracking.

Manages DGI / CNPS / other remittance headers and their detail lines.
Does NOT execute remittance payments or call external systems.

Accounting truth for statutory liabilities lives in the posted payroll journal.
This service tracks settlement facts on top of that truth.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.audit.dto.audit_event_dto import RecordAuditEventCommand
from seeker_accounting.modules.audit.services.audit_service import AuditService
from seeker_accounting.modules.payroll.dto.payroll_remittance_dto import (
    CreatePayrollRemittanceBatchCommand,
    CreatePayrollRemittanceLineCommand,
    PayrollRemittanceBatchDetailDTO,
    PayrollRemittanceBatchListItemDTO,
    PayrollRemittanceLineDTO,
    RecordRemittancePaymentCommand,
    UpdatePayrollRemittanceBatchCommand,
    UpdatePayrollRemittanceLineCommand,
    _ALLOWED_AUTHORITIES,
    _ALLOWED_BATCH_STATUSES,
)
from seeker_accounting.modules.payroll.payroll_permissions import PAYROLL_REMITTANCE_MANAGE
from seeker_accounting.modules.payroll.models.payroll_remittance_batch import (
    PayrollRemittanceBatch,
)
from seeker_accounting.modules.payroll.models.payroll_remittance_line import (
    PayrollRemittanceLine,
)
from seeker_accounting.modules.payroll.repositories.payroll_remittance_repository import (
    PayrollRemittanceBatchRepository,
    PayrollRemittanceLineRepository,
)
from seeker_accounting.modules.payroll.repositories.payroll_run_repository import (
    PayrollRunRepository,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError
from seeker_accounting.platform.numbering.numbering_service import NumberingService

_REMITTANCE_DOC_TYPE = "payroll_remittance"
_EDITABLE_STATUSES = frozenset({"draft", "open"})
_TOLERANCE = Decimal("0.005")
_AUTHORITY_LABELS = {
    "dgi": "DGI (Tax Authority)",
    "cnps": "CNPS (Social Insurance)",
    "other": "Other Authority",
}


class PayrollRemittanceService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        batch_repository_factory: Callable[[Session], PayrollRemittanceBatchRepository],
        line_repository_factory: Callable[[Session], PayrollRemittanceLineRepository],
        run_repository_factory: Callable[[Session], PayrollRunRepository],
        numbering_service: NumberingService,
        permission_service: PermissionService,
        audit_service: AuditService,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._batch_repo_factory = batch_repository_factory
        self._line_repo_factory = line_repository_factory
        self._run_repo_factory = run_repository_factory
        self._numbering_service = numbering_service
        self._permission_service = permission_service
        self._audit_service = audit_service

    # ── Queries ───────────────────────────────────────────────────────────────

    def list_batches(
        self,
        company_id: int,
        authority_code: str | None = None,
        status_code: str | None = None,
    ) -> list[PayrollRemittanceBatchListItemDTO]:
        self._permission_service.require_permission(PAYROLL_REMITTANCE_MANAGE)
        with self._uow_factory() as uow:
            repo = self._batch_repo_factory(uow.session)
            batches = repo.list_by_company(
                company_id, authority_code=authority_code, status_code=status_code
            )
            return [self._to_list_dto(b) for b in batches]

    def get_batch(
        self, company_id: int, batch_id: int
    ) -> PayrollRemittanceBatchDetailDTO:
        self._permission_service.require_permission(PAYROLL_REMITTANCE_MANAGE)
        with self._uow_factory() as uow:
            repo = self._batch_repo_factory(uow.session)
            batch = repo.get_by_id(company_id, batch_id)
            if batch is None:
                raise NotFoundError("Remittance batch not found.")
            return self._to_detail_dto(batch)

    # ── Commands ──────────────────────────────────────────────────────────────

    def create_batch(
        self,
        company_id: int,
        cmd: CreatePayrollRemittanceBatchCommand,
        actor_user_id: int | None = None,
    ) -> PayrollRemittanceBatchDetailDTO:
        self._permission_service.require_permission(PAYROLL_REMITTANCE_MANAGE)
        auth = (cmd.remittance_authority_code or "").lower()
        if auth not in _ALLOWED_AUTHORITIES:
            raise ValidationError(
                f"Invalid authority code '{auth}'. Allowed: {', '.join(sorted(_ALLOWED_AUTHORITIES))}"
            )
        if cmd.period_start_date > cmd.period_end_date:
            raise ValidationError("Period start date must not be after period end date.")

        with self._uow_factory() as uow:
            # Validate linked run if provided
            if cmd.payroll_run_id is not None:
                run = self._run_repo_factory(uow.session).get_by_id(
                    company_id, cmd.payroll_run_id
                )
                if run is None:
                    raise NotFoundError("Linked payroll run not found.")
                if run.status_code != "posted":
                    raise ValidationError(
                        "Remittance batches should only be created for posted payroll runs."
                    )

            batch_number = self._numbering_service.issue_next_number(
                uow.session, company_id, _REMITTANCE_DOC_TYPE
            )
            batch = PayrollRemittanceBatch(
                company_id=company_id,
                batch_number=batch_number,
                payroll_run_id=cmd.payroll_run_id,
                period_start_date=cmd.period_start_date,
                period_end_date=cmd.period_end_date,
                remittance_authority_code=auth,
                amount_due=cmd.amount_due,
                amount_paid=Decimal("0"),
                status_code="draft",
                notes=cmd.notes,
                created_by_user_id=actor_user_id,
                updated_by_user_id=actor_user_id,
            )
            repo = self._batch_repo_factory(uow.session)
            repo.save(batch)
            uow.session.flush()
            self._audit_service.record_event_in_session(
                uow.session,
                company_id,
                RecordAuditEventCommand(
                    event_type_code="PAYROLL_REMITTANCE_BATCH_CREATED",
                    module_code="payroll",
                    entity_type="payroll_remittance_batch",
                    entity_id=batch.id,
                    description=f"Created payroll remittance batch '{batch.batch_number}'.",
                    detail_json=json.dumps(
                        {
                            "authority_code": auth,
                            "amount_due": str(batch.amount_due),
                            "payroll_run_id": batch.payroll_run_id,
                        }
                    ),
                ),
            )
            uow.commit()
            uow.session.refresh(batch)
            return self._to_detail_dto(batch)

    def update_batch(
        self,
        company_id: int,
        batch_id: int,
        cmd: UpdatePayrollRemittanceBatchCommand,
        actor_user_id: int | None = None,
    ) -> PayrollRemittanceBatchDetailDTO:
        self._permission_service.require_permission(PAYROLL_REMITTANCE_MANAGE)
        with self._uow_factory() as uow:
            repo = self._batch_repo_factory(uow.session)
            batch = repo.get_by_id(company_id, batch_id)
            if batch is None:
                raise NotFoundError("Remittance batch not found.")
            if batch.status_code not in _EDITABLE_STATUSES:
                raise ValidationError(
                    f"Batch with status '{batch.status_code}' cannot be edited."
                )
            self._ensure_not_overpaid(cmd.amount_due, Decimal(str(batch.amount_paid)))
            batch.remittance_date = cmd.remittance_date
            batch.amount_due = cmd.amount_due
            batch.reference = cmd.reference
            batch.treasury_transaction_id = cmd.treasury_transaction_id
            batch.notes = cmd.notes
            batch.updated_by_user_id = actor_user_id
            batch.status_code = self._derive_status(batch.amount_due, batch.amount_paid)
            repo.save(batch)
            self._audit_service.record_event_in_session(
                uow.session,
                company_id,
                RecordAuditEventCommand(
                    event_type_code="PAYROLL_REMITTANCE_BATCH_UPDATED",
                    module_code="payroll",
                    entity_type="payroll_remittance_batch",
                    entity_id=batch.id,
                    description=f"Updated payroll remittance batch '{batch.batch_number}'.",
                    detail_json=json.dumps(
                        {
                            "amount_due": str(batch.amount_due),
                            "amount_paid": str(batch.amount_paid),
                            "status_code": batch.status_code,
                        }
                    ),
                ),
            )
            uow.commit()
            uow.session.refresh(batch)
            return self._to_detail_dto(batch)

    def open_batch(self, company_id: int, batch_id: int) -> PayrollRemittanceBatchDetailDTO:
        self._permission_service.require_permission(PAYROLL_REMITTANCE_MANAGE)
        with self._uow_factory() as uow:
            repo = self._batch_repo_factory(uow.session)
            batch = repo.get_by_id(company_id, batch_id)
            if batch is None:
                raise NotFoundError("Remittance batch not found.")
            if batch.status_code != "draft":
                raise ValidationError("Only draft batches can be opened.")
            batch.status_code = "open"
            repo.save(batch)
            self._audit_service.record_event_in_session(
                uow.session,
                company_id,
                RecordAuditEventCommand(
                    event_type_code="PAYROLL_REMITTANCE_BATCH_STATUS_CHANGED",
                    module_code="payroll",
                    entity_type="payroll_remittance_batch",
                    entity_id=batch.id,
                    description=f"Opened payroll remittance batch '{batch.batch_number}'.",
                    detail_json=json.dumps({"status_code": batch.status_code}),
                ),
            )
            uow.commit()
            uow.session.refresh(batch)
            return self._to_detail_dto(batch)

    def record_payment(
        self,
        company_id: int,
        batch_id: int,
        cmd: RecordRemittancePaymentCommand,
        actor_user_id: int | None = None,
    ) -> PayrollRemittanceBatchDetailDTO:
        self._permission_service.require_permission(PAYROLL_REMITTANCE_MANAGE)
        if cmd.amount_paid <= Decimal("0"):
            raise ValidationError("Payment amount must be greater than zero.")

        with self._uow_factory() as uow:
            repo = self._batch_repo_factory(uow.session)
            batch = repo.get_by_id(company_id, batch_id)
            if batch is None:
                raise NotFoundError("Remittance batch not found.")
            if batch.status_code in ("paid", "cancelled"):
                raise ValidationError(
                    f"Batch with status '{batch.status_code}' cannot accept payments."
                )

            new_paid = Decimal(str(batch.amount_paid)) + cmd.amount_paid
            due = Decimal(str(batch.amount_due))
            self._ensure_not_overpaid(due, new_paid)
            batch.amount_paid = new_paid
            batch.remittance_date = cmd.remittance_date
            if cmd.reference:
                batch.reference = cmd.reference
            if cmd.treasury_transaction_id is not None:
                batch.treasury_transaction_id = cmd.treasury_transaction_id
            batch.updated_by_user_id = actor_user_id

            # Compute status from line states or batch totals
            batch.status_code = self._derive_status(due, new_paid)

            repo.save(batch)
            self._audit_service.record_event_in_session(
                uow.session,
                company_id,
                RecordAuditEventCommand(
                    event_type_code="PAYROLL_REMITTANCE_BATCH_STATUS_CHANGED",
                    module_code="payroll",
                    entity_type="payroll_remittance_batch",
                    entity_id=batch.id,
                    description=(
                        f"Recorded payment for payroll remittance batch '{batch.batch_number}'."
                    ),
                    detail_json=json.dumps(
                        {
                            "amount_paid": str(cmd.amount_paid),
                            "total_paid": str(new_paid),
                            "status_code": batch.status_code,
                        }
                    ),
                ),
            )
            uow.commit()
            uow.session.refresh(batch)
            return self._to_detail_dto(batch)

    def cancel_batch(self, company_id: int, batch_id: int) -> None:
        self._permission_service.require_permission(PAYROLL_REMITTANCE_MANAGE)
        with self._uow_factory() as uow:
            repo = self._batch_repo_factory(uow.session)
            batch = repo.get_by_id(company_id, batch_id)
            if batch is None:
                raise NotFoundError("Remittance batch not found.")
            if batch.status_code in ("paid", "cancelled"):
                raise ValidationError(f"Batch is already '{batch.status_code}'.")
            batch.status_code = "cancelled"
            repo.save(batch)
            self._audit_service.record_event_in_session(
                uow.session,
                company_id,
                RecordAuditEventCommand(
                    event_type_code="PAYROLL_REMITTANCE_BATCH_STATUS_CHANGED",
                    module_code="payroll",
                    entity_type="payroll_remittance_batch",
                    entity_id=batch.id,
                    description=f"Cancelled payroll remittance batch '{batch.batch_number}'.",
                    detail_json=json.dumps({"status_code": batch.status_code}),
                ),
            )
            uow.commit()

    # ── Line management ───────────────────────────────────────────────────────

    def add_line(
        self,
        company_id: int,
        batch_id: int,
        cmd: CreatePayrollRemittanceLineCommand,
        actor_user_id: int | None = None,
    ) -> PayrollRemittanceBatchDetailDTO:
        self._permission_service.require_permission(PAYROLL_REMITTANCE_MANAGE)
        if not cmd.description.strip():
            raise ValidationError("Line description is required.")

        with self._uow_factory() as uow:
            batch_repo = self._batch_repo_factory(uow.session)
            batch = batch_repo.get_by_id(company_id, batch_id)
            if batch is None:
                raise NotFoundError("Remittance batch not found.")
            if batch.status_code not in _EDITABLE_STATUSES:
                raise ValidationError("Lines can only be added to draft or open batches.")

            line_repo = self._line_repo_factory(uow.session)
            line_num = line_repo.next_line_number(batch_id)
            line = PayrollRemittanceLine(
                payroll_remittance_batch_id=batch_id,
                line_number=line_num,
                payroll_component_id=cmd.payroll_component_id,
                liability_account_id=cmd.liability_account_id,
                description=cmd.description.strip(),
                amount_due=cmd.amount_due,
                amount_paid=Decimal("0"),
                status_code="open",
                notes=cmd.notes,
            )
            line_repo.save(line)
            uow.session.flush()
            self._audit_service.record_event_in_session(
                uow.session,
                company_id,
                RecordAuditEventCommand(
                    event_type_code="PAYROLL_REMITTANCE_BATCH_UPDATED",
                    module_code="payroll",
                    entity_type="payroll_remittance_batch",
                    entity_id=batch.id,
                    description=f"Added line {line.line_number} to remittance batch '{batch.batch_number}'.",
                    detail_json=json.dumps(
                        {
                            "line_id": line.id,
                            "amount_due": str(line.amount_due),
                            "status_code": line.status_code,
                        }
                    ),
                ),
            )
            uow.commit()
            uow.session.refresh(batch)
            return self._to_detail_dto(batch)

    def update_line(
        self,
        company_id: int,
        batch_id: int,
        line_id: int,
        cmd: UpdatePayrollRemittanceLineCommand,
    ) -> PayrollRemittanceBatchDetailDTO:
        self._permission_service.require_permission(PAYROLL_REMITTANCE_MANAGE)
        if not cmd.description.strip():
            raise ValidationError("Line description is required.")

        with self._uow_factory() as uow:
            batch_repo = self._batch_repo_factory(uow.session)
            batch = batch_repo.get_by_id(company_id, batch_id)
            if batch is None:
                raise NotFoundError("Remittance batch not found.")
            if batch.status_code not in _EDITABLE_STATUSES:
                raise ValidationError("Lines can only be updated on draft or open batches.")

            line_repo = self._line_repo_factory(uow.session)
            line = line_repo.get_by_id(line_id)
            if line is None or line.payroll_remittance_batch_id != batch_id:
                raise NotFoundError("Remittance line not found.")

            previous_amount_paid = Decimal(str(line.amount_paid))
            previous_status = line.status_code
            line.description = cmd.description.strip()
            self._ensure_not_overpaid(cmd.amount_due, cmd.amount_paid)
            line.amount_due = cmd.amount_due
            line.amount_paid = cmd.amount_paid
            line.status_code = self._derive_status(line.amount_due, line.amount_paid)
            line.notes = cmd.notes
            line_repo.save(line)
            event_type = (
                "PAYROLL_REMITTANCE_LINE_SETTLEMENT_CHANGED"
                if previous_amount_paid != cmd.amount_paid or previous_status != line.status_code
                else "PAYROLL_REMITTANCE_BATCH_UPDATED"
            )
            self._audit_service.record_event_in_session(
                uow.session,
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type,
                    module_code="payroll",
                    entity_type="payroll_remittance_line",
                    entity_id=line.id,
                    description=(
                        f"Updated remittance line {line.line_number} on batch '{batch.batch_number}'."
                    ),
                    detail_json=json.dumps(
                        {
                            "amount_due": str(line.amount_due),
                            "amount_paid": str(line.amount_paid),
                            "status_code": line.status_code,
                        }
                    ),
                ),
            )
            uow.commit()
            uow.session.refresh(batch)
            return self._to_detail_dto(batch)

    def remove_line(
        self, company_id: int, batch_id: int, line_id: int
    ) -> PayrollRemittanceBatchDetailDTO:
        self._permission_service.require_permission(PAYROLL_REMITTANCE_MANAGE)
        with self._uow_factory() as uow:
            batch_repo = self._batch_repo_factory(uow.session)
            batch = batch_repo.get_by_id(company_id, batch_id)
            if batch is None:
                raise NotFoundError("Remittance batch not found.")
            if batch.status_code not in _EDITABLE_STATUSES:
                raise ValidationError("Lines can only be removed from draft or open batches.")

            line_repo = self._line_repo_factory(uow.session)
            line = line_repo.get_by_id(line_id)
            if line is None or line.payroll_remittance_batch_id != batch_id:
                raise NotFoundError("Remittance line not found.")
            line_repo.delete(line)
            self._audit_service.record_event_in_session(
                uow.session,
                company_id,
                RecordAuditEventCommand(
                    event_type_code="PAYROLL_REMITTANCE_BATCH_UPDATED",
                    module_code="payroll",
                    entity_type="payroll_remittance_batch",
                    entity_id=batch.id,
                    description=f"Removed remittance line {line_id} from batch '{batch.batch_number}'.",
                    detail_json=json.dumps({"line_id": line_id}),
                ),
            )
            uow.commit()
            uow.session.refresh(batch)
            return self._to_detail_dto(batch)

    @staticmethod
    def _ensure_not_overpaid(amount_due: Decimal | object, amount_paid: Decimal | object) -> None:
        due = Decimal(str(amount_due))
        paid = Decimal(str(amount_paid))
        if paid > due + _TOLERANCE:
            raise ValidationError(
                "Paid amount exceeds due amount beyond tolerance. "
                f"Due={due:.4f}, Paid={paid:.4f}."
            )

    @staticmethod
    def _derive_status(amount_due: Decimal | object, amount_paid: Decimal | object) -> str:
        due = Decimal(str(amount_due))
        paid = Decimal(str(amount_paid))
        if paid <= _TOLERANCE:
            return "open"
        if paid >= due - _TOLERANCE:
            return "paid"
        return "partial"

    # ── DTO helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _to_list_dto(b: PayrollRemittanceBatch) -> PayrollRemittanceBatchListItemDTO:
        due = Decimal(str(b.amount_due))
        paid = Decimal(str(b.amount_paid))
        return PayrollRemittanceBatchListItemDTO(
            id=b.id,
            company_id=b.company_id,
            batch_number=b.batch_number,
            payroll_run_id=b.payroll_run_id,
            payroll_run_reference=b.payroll_run.run_reference if b.payroll_run else None,
            period_start_date=b.period_start_date,
            period_end_date=b.period_end_date,
            remittance_authority_code=b.remittance_authority_code,
            remittance_date=b.remittance_date,
            amount_due=due,
            amount_paid=paid,
            outstanding=max(due - paid, Decimal("0")),
            status_code=b.status_code,
        )

    @staticmethod
    def _to_detail_dto(b: PayrollRemittanceBatch) -> PayrollRemittanceBatchDetailDTO:
        due = Decimal(str(b.amount_due))
        paid = Decimal(str(b.amount_paid))
        lines = tuple(
            PayrollRemittanceLine_to_dto(ln) for ln in sorted(b.lines, key=lambda l: l.line_number)
        )
        return PayrollRemittanceBatchDetailDTO(
            id=b.id,
            company_id=b.company_id,
            batch_number=b.batch_number,
            payroll_run_id=b.payroll_run_id,
            payroll_run_reference=b.payroll_run.run_reference if b.payroll_run else None,
            period_start_date=b.period_start_date,
            period_end_date=b.period_end_date,
            remittance_authority_code=b.remittance_authority_code,
            remittance_date=b.remittance_date,
            amount_due=due,
            amount_paid=paid,
            outstanding=max(due - paid, Decimal("0")),
            status_code=b.status_code,
            reference=b.reference,
            treasury_transaction_id=b.treasury_transaction_id,
            notes=b.notes,
            lines=lines,
        )


def PayrollRemittanceLine_to_dto(ln: PayrollRemittanceLine) -> PayrollRemittanceLineDTO:
    due = Decimal(str(ln.amount_due))
    paid = Decimal(str(ln.amount_paid))
    comp = ln.payroll_component
    acct = ln.liability_account
    return PayrollRemittanceLineDTO(
        id=ln.id,
        payroll_remittance_batch_id=ln.payroll_remittance_batch_id,
        line_number=ln.line_number,
        payroll_component_id=ln.payroll_component_id,
        payroll_component_name=comp.component_name if comp else None,
        liability_account_id=ln.liability_account_id,
        liability_account_code=acct.account_code if acct else None,
        description=ln.description,
        amount_due=due,
        amount_paid=paid,
        outstanding=max(due - paid, Decimal("0")),
        status_code=ln.status_code,
        notes=ln.notes,
    )
