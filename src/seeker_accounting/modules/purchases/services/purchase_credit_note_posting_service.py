from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.app.context.app_context import AppContext
from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.accounting.chart_of_accounts.repositories.account_repository import AccountRepository
from seeker_accounting.modules.accounting.fiscal_periods.repositories.fiscal_period_repository import (
    FiscalPeriodRepository,
)
from seeker_accounting.modules.accounting.journals.models.journal_entry import JournalEntry
from seeker_accounting.modules.accounting.journals.models.journal_entry_line import JournalEntryLine
from seeker_accounting.modules.accounting.journals.repositories.journal_entry_repository import (
    JournalEntryRepository,
)
from seeker_accounting.modules.accounting.reference_data.repositories.account_role_mapping_repository import (
    AccountRoleMappingRepository,
)
from seeker_accounting.modules.accounting.reference_data.repositories.tax_code_account_mapping_repository import (
    TaxCodeAccountMappingRepository,
)
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.audit import event_type_catalog
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.purchases.dto.purchase_credit_note_dto import PurchasePostingCreditNoteResultDTO
from seeker_accounting.modules.purchases.repositories.purchase_credit_note_repository import (
    PurchaseCreditNoteRepository,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, PeriodLockedError, ValidationError
from seeker_accounting.platform.exceptions.app_error_codes import AppErrorCode
from seeker_accounting.platform.numbering.numbering_service import NumberingService

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

AccountRepositoryFactory = Callable[[Session], AccountRepository]
FiscalPeriodRepositoryFactory = Callable[[Session], FiscalPeriodRepository]
JournalEntryRepositoryFactory = Callable[[Session], JournalEntryRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
PurchaseCreditNoteRepositoryFactory = Callable[[Session], PurchaseCreditNoteRepository]
AccountRoleMappingRepositoryFactory = Callable[[Session], AccountRoleMappingRepository]
TaxCodeAccountMappingRepositoryFactory = Callable[[Session], TaxCodeAccountMappingRepository]


class PurchaseCreditNotePostingService:
    DOCUMENT_TYPE_CODE = "PURCHASE_CREDIT_NOTE"

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        app_context: AppContext,
        credit_note_repository_factory: PurchaseCreditNoteRepositoryFactory,
        journal_entry_repository_factory: JournalEntryRepositoryFactory,
        account_repository_factory: AccountRepositoryFactory,
        fiscal_period_repository_factory: FiscalPeriodRepositoryFactory,
        account_role_mapping_repository_factory: AccountRoleMappingRepositoryFactory,
        tax_code_account_mapping_repository_factory: TaxCodeAccountMappingRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        numbering_service: NumberingService,
        permission_service: PermissionService,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._app_context = app_context
        self._credit_note_repository_factory = credit_note_repository_factory
        self._journal_entry_repository_factory = journal_entry_repository_factory
        self._account_repository_factory = account_repository_factory
        self._fiscal_period_repository_factory = fiscal_period_repository_factory
        self._account_role_mapping_repository_factory = account_role_mapping_repository_factory
        self._tax_code_account_mapping_repository_factory = tax_code_account_mapping_repository_factory
        self._company_repository_factory = company_repository_factory
        self._numbering_service = numbering_service
        self._permission_service = permission_service
        self._audit_service = audit_service

    def post_credit_note(
        self,
        company_id: int,
        credit_note_id: int,
        actor_user_id: int | None = None,
    ) -> PurchasePostingCreditNoteResultDTO:
        self._permission_service.require_permission("purchases.credit_notes.post")
        with self._unit_of_work_factory() as uow:
            actor_id = actor_user_id if actor_user_id is not None else self._app_context.current_user_id
            self._require_company(uow.session, company_id)

            cn_repo = self._credit_note_repository_factory(uow.session)
            journal_repo = self._journal_entry_repository_factory(uow.session)
            fiscal_repo = self._fiscal_period_repository_factory(uow.session)
            role_mapping_repo = self._account_role_mapping_repository_factory(uow.session)
            tax_mapping_repo = self._tax_code_account_mapping_repository_factory(uow.session)

            cn = cn_repo.get_detail(company_id, credit_note_id)
            if cn is None:
                raise NotFoundError(f"Purchase credit note {credit_note_id} not found.")
            if cn.status_code != "draft":
                raise ValidationError("Only draft credit notes can be posted.")
            if not cn.lines:
                raise ValidationError("Credit note must have at least one line to be posted.")

            # --- Period validation ---
            fiscal_period = fiscal_repo.get_covering_date(company_id, cn.credit_date)
            if fiscal_period is None:
                raise ValidationError("Credit note date must fall within an existing fiscal period.")
            if fiscal_period.status_code == "LOCKED":
                raise PeriodLockedError("Credit note cannot be posted into a locked fiscal period.")
            if fiscal_period.status_code != "OPEN":
                raise ValidationError("Credit note can only be posted into an open fiscal period.")

            # --- AP control account ---
            ap_mapping = role_mapping_repo.get_by_role_code(company_id, "ap_control")
            if ap_mapping is None:
                raise ValidationError(
                    "An AP control account mapping must be configured before posting credit notes.",
                    app_error_code=AppErrorCode.MISSING_ACCOUNT_ROLE_MAPPING,
                    context={
                        "company_id": company_id,
                        "role_code": "ap_control",
                        "origin_workflow": "purchase_credit_note",
                    },
                )
            ap_account_id = ap_mapping.account_id

            # --- Build journal lines (reverse of purchase bill) ---
            # Purchase bill: DR Expense, DR Input VAT, CR AP
            # Credit Note:   DR AP (reduces AP), CR Expense, CR Input VAT
            journal_lines: list[JournalEntryLine] = []
            line_number = 1

            # Debit AP control (reduces liability)
            journal_lines.append(
                JournalEntryLine(
                    journal_entry_id=0,
                    line_number=line_number,
                    account_id=ap_account_id,
                    line_description=f"AP reduction - Credit note {cn.credit_number}",
                    debit_amount=cn.total_amount,
                    credit_amount=Decimal("0.00"),
                )
            )
            line_number += 1

            # Credit expense accounts (reduces expense)
            expense_credits: dict[int, Decimal] = {}
            tax_credits: dict[int, Decimal] = {}

            for cn_line in cn.lines:
                if cn_line.expense_account_id is not None:
                    expense_credits[cn_line.expense_account_id] = (
                        expense_credits.get(cn_line.expense_account_id, Decimal("0.00"))
                        + cn_line.line_subtotal_amount
                    )
                if cn_line.tax_code_id is not None and cn_line.line_tax_amount > Decimal("0.00"):
                    tax_mapping = tax_mapping_repo.get_by_tax_code(company_id, cn_line.tax_code_id)
                    if tax_mapping is None or tax_mapping.tax_asset_account_id is None:
                        raise ValidationError(
                            f"Tax account mapping for tax code on line {cn_line.line_number} "
                            "must be configured before posting."
                        )
                    tax_account_id = tax_mapping.tax_asset_account_id
                    tax_credits[tax_account_id] = (
                        tax_credits.get(tax_account_id, Decimal("0.00"))
                        + cn_line.line_tax_amount
                    )

            for exp_account_id, amount in expense_credits.items():
                journal_lines.append(
                    JournalEntryLine(
                        journal_entry_id=0,
                        line_number=line_number,
                        account_id=exp_account_id,
                        line_description=f"Expense reduction - Credit note {cn.credit_number}",
                        debit_amount=Decimal("0.00"),
                        credit_amount=amount,
                    )
                )
                line_number += 1

            for tax_account_id, amount in tax_credits.items():
                journal_lines.append(
                    JournalEntryLine(
                        journal_entry_id=0,
                        line_number=line_number,
                        account_id=tax_account_id,
                        line_description=f"Input VAT reduction - Credit note {cn.credit_number}",
                        debit_amount=Decimal("0.00"),
                        credit_amount=amount,
                    )
                )
                line_number += 1

            # --- Create journal entry ---
            journal_entry = JournalEntry(
                company_id=company_id,
                fiscal_period_id=fiscal_period.id,
                entry_number=None,
                entry_date=cn.credit_date,
                journal_type_code="PURCHASES",
                reference_text=cn.credit_number,
                description=f"Purchase credit note {cn.credit_number}",
                source_module_code="purchases",
                source_document_type="purchase_credit_note",
                source_document_id=cn.id,
                status_code="POSTED",
                posted_at=datetime.utcnow(),
                posted_by_user_id=actor_id,
                created_by_user_id=actor_id,
            )
            journal_repo.add(journal_entry)
            uow.session.flush()

            journal_entry.entry_number = self._numbering_service.issue_next_number(
                uow.session,
                company_id=company_id,
                document_type_code="JOURNAL_ENTRY",
            )
            journal_repo.save(journal_entry)

            for jl in journal_lines:
                jl.journal_entry_id = journal_entry.id
            uow.session.add_all(journal_lines)

            # --- Assign credit note number and update status ---
            cn.credit_number = f"PCN-{cn.id:06d}"
            cn.status_code = "posted"
            cn.posted_journal_entry_id = journal_entry.id
            cn.posted_at = datetime.utcnow()
            cn.posted_by_user_id = actor_id
            cn_repo.save(cn)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ConflictError("Failed to post credit note: possible duplicate.") from exc

            self._try_record_audit(
                    company_id,
                    event_type_catalog.PURCHASE_CREDIT_NOTE_POSTED,
                    "purchase_credit_note",
                    cn.id,
                    f"Purchase credit note {cn.credit_number} posted.",
                )

            return PurchasePostingCreditNoteResultDTO(
                credit_note_id=cn.id,
                credit_number=cn.credit_number,
                journal_entry_id=journal_entry.id,
                status_code=cn.status_code,
            )

    def _require_company(self, session: Session, company_id: int) -> None:
        repo = self._company_repository_factory(session)
        if repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company {company_id} not found.")

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
