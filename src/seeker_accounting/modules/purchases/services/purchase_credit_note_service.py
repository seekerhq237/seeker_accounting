from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from sqlalchemy.orm import Session

from seeker_accounting.app.context.app_context import AppContext
from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.audit import event_type_catalog
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.purchases.dto.purchase_credit_note_commands import (
    CreatePurchaseCreditNoteCommand,
    PurchaseCreditNoteLineCommand,
    UpdatePurchaseCreditNoteCommand,
)
from seeker_accounting.modules.purchases.dto.purchase_credit_note_dto import (
    PurchaseCreditNoteDetailDTO,
    PurchaseCreditNoteListItemDTO,
)
from seeker_accounting.modules.purchases.models.purchase_credit_note import PurchaseCreditNote
from seeker_accounting.modules.purchases.models.purchase_credit_note_line import PurchaseCreditNoteLine
from seeker_accounting.modules.purchases.repositories.purchase_credit_note_line_repository import (
    PurchaseCreditNoteLineRepository,
)
from seeker_accounting.modules.purchases.repositories.purchase_credit_note_repository import (
    PurchaseCreditNoteRepository,
)
from seeker_accounting.modules.suppliers.repositories.supplier_repository import SupplierRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
SupplierRepositoryFactory = Callable[[Session], SupplierRepository]
PurchaseCreditNoteRepositoryFactory = Callable[[Session], PurchaseCreditNoteRepository]
PurchaseCreditNoteLineRepositoryFactory = Callable[[Session], PurchaseCreditNoteLineRepository]


class PurchaseCreditNoteService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        app_context: AppContext,
        credit_note_repository_factory: PurchaseCreditNoteRepositoryFactory,
        credit_note_line_repository_factory: PurchaseCreditNoteLineRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        supplier_repository_factory: SupplierRepositoryFactory,
        permission_service: PermissionService,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._app_context = app_context
        self._credit_note_repository_factory = credit_note_repository_factory
        self._credit_note_line_repository_factory = credit_note_line_repository_factory
        self._company_repository_factory = company_repository_factory
        self._supplier_repository_factory = supplier_repository_factory
        self._permission_service = permission_service
        self._audit_service = audit_service

    # ─── Queries ──────────────────────────────────────────────────────────

    def list_credit_notes(
        self,
        company_id: int,
        *,
        status_code: str | None = None,
        supplier_id: int | None = None,
    ) -> list[PurchaseCreditNoteListItemDTO]:
        self._permission_service.require_permission("purchases.credit_notes.view")
        with self._unit_of_work_factory() as uow:
            repo = self._credit_note_repository_factory(uow.session)
            return repo.list_by_company(company_id, status_code=status_code, supplier_id=supplier_id)

    def get_credit_note(self, company_id: int, credit_note_id: int) -> PurchaseCreditNoteDetailDTO:
        self._permission_service.require_permission("purchases.credit_notes.view")
        with self._unit_of_work_factory() as uow:
            repo = self._credit_note_repository_factory(uow.session)
            cn = repo.get_detail(company_id, credit_note_id)
            if cn is None:
                raise NotFoundError(f"Purchase credit note {credit_note_id} not found.")
            return PurchaseCreditNoteRepository._to_detail_dto(cn)

    # ─── Mutations ────────────────────────────────────────────────────────

    def create_draft_credit_note(self, cmd: CreatePurchaseCreditNoteCommand) -> PurchaseCreditNoteDetailDTO:
        self._permission_service.require_permission("purchases.credit_notes.create")
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, cmd.company_id)
            self._require_supplier(uow.session, cmd.company_id, cmd.supplier_id)

            lines = self._validate_and_build_lines(cmd.lines)
            subtotal, tax_total, grand_total = self._compute_totals(lines)

            cn = PurchaseCreditNote(
                company_id=cmd.company_id,
                credit_number="PCN-DRAFT-PENDING",
                supplier_id=cmd.supplier_id,
                supplier_credit_reference=cmd.supplier_credit_reference,
                credit_date=cmd.credit_date,
                currency_code=cmd.currency_code,
                exchange_rate=cmd.exchange_rate,
                status_code="draft",
                reason_text=cmd.reason_text,
                source_bill_id=cmd.source_bill_id,
                subtotal_amount=subtotal,
                tax_amount=tax_total,
                total_amount=grand_total,
                contract_id=cmd.contract_id,
                project_id=cmd.project_id,
            )
            repo = self._credit_note_repository_factory(uow.session)
            repo.add(cn)

            cn.credit_number = self._format_draft_number(cn.id)
            for ln in lines:
                ln.purchase_credit_note_id = cn.id
            repo.save(cn)

            line_repo = self._credit_note_line_repository_factory(uow.session)
            for ln in lines:
                line_repo.add(ln)

            uow.commit()

            self._try_record_audit(
                    cmd.company_id,
                    event_type_catalog.PURCHASE_CREDIT_NOTE_CREATED,
                    "purchase_credit_note",
                    cn.id,
                    f"Purchase credit note {cn.credit_number} created.",
                )

            with self._unit_of_work_factory() as uow2:
                repo2 = self._credit_note_repository_factory(uow2.session)
                refreshed = repo2.get_detail(cmd.company_id, cn.id)
                return PurchaseCreditNoteRepository._to_detail_dto(refreshed)

    def update_draft_credit_note(self, cmd: UpdatePurchaseCreditNoteCommand) -> PurchaseCreditNoteDetailDTO:
        self._permission_service.require_permission("purchases.credit_notes.edit")
        with self._unit_of_work_factory() as uow:
            repo = self._credit_note_repository_factory(uow.session)
            cn = repo.get_by_id(cmd.company_id, cmd.credit_note_id)
            if cn is None:
                raise NotFoundError(f"Purchase credit note {cmd.credit_note_id} not found.")
            if cn.status_code != "draft":
                raise ConflictError("Only draft credit notes can be edited.")

            self._require_supplier(uow.session, cmd.company_id, cmd.supplier_id)

            lines = self._validate_and_build_lines(cmd.lines)
            subtotal, tax_total, grand_total = self._compute_totals(lines)

            cn.supplier_id = cmd.supplier_id
            cn.supplier_credit_reference = cmd.supplier_credit_reference
            cn.credit_date = cmd.credit_date
            cn.currency_code = cmd.currency_code
            cn.exchange_rate = cmd.exchange_rate
            cn.reason_text = cmd.reason_text
            cn.source_bill_id = cmd.source_bill_id
            cn.subtotal_amount = subtotal
            cn.tax_amount = tax_total
            cn.total_amount = grand_total
            cn.contract_id = cmd.contract_id
            cn.project_id = cmd.project_id

            for ln in lines:
                ln.purchase_credit_note_id = cn.id

            line_repo = self._credit_note_line_repository_factory(uow.session)
            line_repo.replace_lines(cmd.company_id, cn.id, lines)
            repo.save(cn)
            uow.commit()

            self._try_record_audit(
                    cmd.company_id,
                    event_type_catalog.PURCHASE_CREDIT_NOTE_UPDATED,
                    "purchase_credit_note",
                    cn.id,
                    f"Purchase credit note {cn.credit_number} updated.",
                )

            with self._unit_of_work_factory() as uow2:
                repo2 = self._credit_note_repository_factory(uow2.session)
                refreshed = repo2.get_detail(cmd.company_id, cn.id)
                return PurchaseCreditNoteRepository._to_detail_dto(refreshed)

    def cancel_credit_note(
        self,
        company_id: int,
        credit_note_id: int,
        actor_user_id: int | None = None,
    ) -> None:
        self._permission_service.require_permission("purchases.credit_notes.cancel")
        with self._unit_of_work_factory() as uow:
            repo = self._credit_note_repository_factory(uow.session)
            cn = repo.get_by_id(company_id, credit_note_id)
            if cn is None:
                raise NotFoundError(f"Purchase credit note {credit_note_id} not found.")
            if cn.status_code == "cancelled":
                raise ConflictError("Credit note is already cancelled.")
            if cn.status_code == "posted":
                raise ValidationError(
                    "Posted credit notes cannot be cancelled directly. "
                    "Issue a reversing credit note if needed."
                )
            cn.status_code = "cancelled"
            repo.save(cn)
            uow.commit()

            self._try_record_audit(
                    company_id,
                    event_type_catalog.PURCHASE_CREDIT_NOTE_CANCELLED,
                    "purchase_credit_note",
                    credit_note_id,
                    f"Purchase credit note {cn.credit_number} cancelled.",
                )

    # ─── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _format_draft_number(credit_note_id: int) -> str:
        return f"PCN-DRAFT-{credit_note_id:06d}"

    @staticmethod
    def _validate_and_build_lines(
        line_cmds: list[PurchaseCreditNoteLineCommand],
    ) -> list[PurchaseCreditNoteLine]:
        if not line_cmds:
            raise ValidationError("A credit note must have at least one line.")
        lines: list[PurchaseCreditNoteLine] = []
        for idx, lc in enumerate(line_cmds, start=1):
            if not lc.description.strip():
                raise ValidationError(f"Line {idx}: description is required.")
            subtotal = lc.line_subtotal_amount.quantize(Decimal("0.01"))
            if subtotal < Decimal("0"):
                raise ValidationError(f"Line {idx}: subtotal amount cannot be negative.")

            lines.append(
                PurchaseCreditNoteLine(
                    purchase_credit_note_id=0,
                    line_number=idx,
                    description=lc.description,
                    quantity=lc.quantity,
                    unit_cost=lc.unit_cost,
                    expense_account_id=lc.expense_account_id,
                    tax_code_id=lc.tax_code_id,
                    line_subtotal_amount=subtotal,
                    line_tax_amount=Decimal("0.00"),
                    line_total_amount=subtotal,
                    contract_id=lc.contract_id,
                    project_id=lc.project_id,
                    project_job_id=lc.project_job_id,
                    project_cost_code_id=lc.project_cost_code_id,
                )
            )
        return lines

    @staticmethod
    def _compute_totals(
        lines: list[PurchaseCreditNoteLine],
    ) -> tuple[Decimal, Decimal, Decimal]:
        subtotal = sum((ln.line_subtotal_amount for ln in lines), Decimal("0.00"))
        tax_total = sum((ln.line_tax_amount for ln in lines), Decimal("0.00"))
        grand_total = subtotal + tax_total
        return subtotal, tax_total, grand_total

    def _require_company(self, session: Session, company_id: int) -> None:
        repo = self._company_repository_factory(session)
        if repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company {company_id} not found.")

    def _require_supplier(self, session: Session, company_id: int, supplier_id: int) -> None:
        repo = self._supplier_repository_factory(session)
        if repo.get_by_id(company_id, supplier_id) is None:
            raise NotFoundError(f"Supplier {supplier_id} not found.")

    def _try_record_audit(
        self,
        company_id: int,
        event_type_code: str,
        entity_type: str,
        entity_id: int,
        description: str,
    ) -> None:
        if self._audit_service is None:
            return
        from seeker_accounting.modules.audit.dto.audit_event_dto import RecordAuditEventCommand
        from seeker_accounting.modules.audit.event_type_catalog import MODULE_PURCHASES
        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type_code,
                    module_code=MODULE_PURCHASES,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    description=description,
                ),
            )
        except Exception:
            pass
