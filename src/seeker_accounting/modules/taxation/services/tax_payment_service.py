"""Service for tax payments (settlements against tax returns)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.app.context.app_context import AppContext
from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.accounting.chart_of_accounts.repositories.account_repository import (
    AccountRepository,
)
from seeker_accounting.modules.accounting.fiscal_periods.repositories.fiscal_period_repository import (
    FiscalPeriodRepository,
)
from seeker_accounting.modules.accounting.journals.models.journal_entry import (
    JournalEntry,
)
from seeker_accounting.modules.accounting.journals.models.journal_entry_line import (
    JournalEntryLine,
)
from seeker_accounting.modules.accounting.journals.repositories.journal_entry_repository import (
    JournalEntryRepository,
)
from seeker_accounting.modules.administration.services.permission_service import (
    PermissionService,
)
from seeker_accounting.modules.companies.repositories.company_repository import (
    CompanyRepository,
)
from seeker_accounting.modules.taxation.constants import (
    ALL_ASSESSED_RETURN_TAX_TYPES,
    ALL_TAX_PAYMENT_METHODS,
    ASSESSED_PAYMENT_DEBIT_ACCOUNT_CODE_BY_TAX_TYPE,
    OBLIGATION_STATUS_PAID,
    RETURN_STATUS_CANCELLED,
    SETTLEMENT_VAT_PAYABLE_ACCOUNT_CODE,
    TAX_TYPE_VAT,
)
from seeker_accounting.modules.taxation.dto.tax_compliance_dto import (
    RecordTaxPaymentCommand,
    TaxPaymentDTO,
)
from seeker_accounting.modules.taxation.models.tax_payment import TaxPayment
from seeker_accounting.modules.taxation.repositories.tax_payment_repository import (
    TaxPaymentRepository,
)
from seeker_accounting.modules.taxation.repositories.tax_return_repository import (
    TaxReturnRepository,
)
from seeker_accounting.platform.exceptions import (
    ConflictError,
    NotFoundError,
    PeriodLockedError,
    ValidationError,
)

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService
    from seeker_accounting.platform.numbering.numbering_service import (
        NumberingService,
    )


TaxPaymentRepositoryFactory = Callable[[Session], TaxPaymentRepository]
TaxReturnRepositoryFactory = Callable[[Session], TaxReturnRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
AccountRepositoryFactory = Callable[[Session], AccountRepository]
FiscalPeriodRepositoryFactory = Callable[[Session], FiscalPeriodRepository]
JournalEntryRepositoryFactory = Callable[[Session], JournalEntryRepository]


_ZERO = Decimal("0.00")
_JOURNAL_DOC_TYPE = "JOURNAL_ENTRY"
_JOURNAL_TYPE_CODE_OD = "OD"  # Opérations Diverses


class TaxPaymentService:
    PERMISSION_VIEW = "taxation.payments.view"
    PERMISSION_MANAGE = "taxation.payments.manage"

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        app_context: AppContext,
        tax_payment_repository_factory: TaxPaymentRepositoryFactory,
        tax_return_repository_factory: TaxReturnRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        permission_service: PermissionService,
        audit_service: "AuditService | None" = None,
        *,
        account_repository_factory: AccountRepositoryFactory | None = None,
        fiscal_period_repository_factory: FiscalPeriodRepositoryFactory | None = None,
        journal_entry_repository_factory: JournalEntryRepositoryFactory | None = None,
        numbering_service: "NumberingService | None" = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._app_context = app_context
        self._tax_payment_repository_factory = tax_payment_repository_factory
        self._tax_return_repository_factory = tax_return_repository_factory
        self._company_repository_factory = company_repository_factory
        self._permission_service = permission_service
        self._audit_service = audit_service
        self._account_repository_factory = account_repository_factory
        self._fiscal_period_repository_factory = fiscal_period_repository_factory
        self._journal_entry_repository_factory = journal_entry_repository_factory
        self._numbering_service = numbering_service

    # ---------------- Read ----------------

    def list_payments_for_return(
        self, company_id: int, return_id: int
    ) -> list[TaxPaymentDTO]:
        self._permission_service.require_permission(self.PERMISSION_VIEW)
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._tax_payment_repository_factory(uow.session)
            payments = repo.list_by_return(company_id, return_id)
            return [self._to_dto(p) for p in payments]

    # ---------------- Write ----------------

    def record_payment(
        self,
        company_id: int,
        command: RecordTaxPaymentCommand,
        actor_user_id: int | None = None,
    ) -> TaxPaymentDTO:
        self._permission_service.require_permission(self.PERMISSION_MANAGE)

        if command.amount is None or Decimal(command.amount) <= _ZERO:
            raise ValidationError("Payment amount must be greater than zero.")
        amount = Decimal(command.amount).quantize(Decimal("0.01"))

        method = (command.payment_method_code or "").strip().upper()
        if method not in ALL_TAX_PAYMENT_METHODS:
            raise ValidationError(
                f"Payment method '{command.payment_method_code}' is not recognized.",
            )

        if command.payment_date is None:
            raise ValidationError("Payment date is required.")

        reference = (command.reference or "").strip() or None
        notes = (command.notes or "").strip() or None
        if reference is not None and len(reference) > 120:
            raise ValidationError("Reference is too long (max 120 characters).")
        if notes is not None and len(notes) > 500:
            raise ValidationError("Notes are too long (max 500 characters).")

        actor_id = (
            actor_user_id
            if actor_user_id is not None
            else self._app_context.current_user_id
        )

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)

            return_repo = self._tax_return_repository_factory(uow.session)
            tax_return = return_repo.get_by_id(company_id, command.tax_return_id)
            if tax_return is None:
                raise NotFoundError(
                    f"Tax return {command.tax_return_id} was not found.",
                )
            if tax_return.status_code == RETURN_STATUS_CANCELLED:
                raise ValidationError(
                    "Cannot record payments against a cancelled return.",
                )
            if command.payment_date < tax_return.period_start:
                raise ValidationError(
                    "Payment date cannot fall before the return period.",
                )

            payment_repo = self._tax_payment_repository_factory(uow.session)
            payment = TaxPayment(
                company_id=company_id,
                tax_return_id=tax_return.id,
                payment_date=command.payment_date,
                amount=amount,
                payment_method_code=method,
                reference=reference,
                notes=notes,
                recorded_by_user_id=actor_id,
            )
            payment_repo.add(payment)

            # Bank-side journal entry (T16) — Dr 4441 / Cr treasury.
            posted_journal_id: int | None = None
            if command.treasury_account_id is not None:
                posted_journal_id = self._post_bank_side_journal(
                    uow.session,
                    company_id=company_id,
                    tax_return=tax_return,
                    payment=payment,
                    treasury_account_id=command.treasury_account_id,
                    payment_date=command.payment_date,
                    amount=amount,
                    method=method,
                    reference=reference,
                    actor_id=actor_id,
                )
                payment.journal_entry_id = posted_journal_id

            # Update return total_paid and obligation status when fully settled.
            tax_return.total_paid_amount = (tax_return.total_paid_amount or _ZERO) + amount
            if (
                tax_return.total_due_amount is not None
                and tax_return.total_paid_amount >= tax_return.total_due_amount
                and tax_return.obligation is not None
            ):
                tax_return.obligation.status_code = OBLIGATION_STATUS_PAID

            try:
                uow.commit()
            except IntegrityError as exc:  # pragma: no cover - defensive
                raise ConflictError(
                    "Tax payment could not be saved due to a data conflict.",
                ) from exc

            self._record_audit(
                company_id,
                payment.id,
                f"Recorded {amount} payment via {method} on "
                f"{command.payment_date.isoformat()}.",
                event_type_code="TAX_PAYMENT_RECORDED",
            )
            if posted_journal_id is not None:
                self._record_audit(
                    company_id,
                    payment.id,
                    (
                        f"Posted bank-side JE for payment {amount} on "
                        f"{command.payment_date.isoformat()} "
                        f"(journal_entry_id={posted_journal_id})."
                    ),
                    event_type_code="TAX_PAYMENT_POSTED",
                )

            return self._to_dto(payment)

    # ---------------- Helpers ----------------

    def _post_bank_side_journal(
        self,
        session: Session,
        *,
        company_id: int,
        tax_return,
        payment: TaxPayment,
        treasury_account_id: int,
        payment_date,
        amount: Decimal,
        method: str,
        reference: str | None,
        actor_id: int | None,
    ) -> int:
        """Post the bank-side JE for a tax payment.

        Dispatch by ``tax_return.tax_type_code``:

        - VAT: Dr 4441 (VAT payable) / Cr <treasury>.  The return
          must have been settled (T15) before payments are posted.
        - Patente / TSR / Customs (T27): Dr <type-specific account>
          / Cr <treasury>.  No settlement step exists for these tax
          types — the assessed-amount return is created already in
          the FILED state.
        - Other tax types: rejected.  CIT and payroll-derived taxes
          have their own posting flows in their owning modules.
        """

        if (
            self._account_repository_factory is None
            or self._fiscal_period_repository_factory is None
            or self._journal_entry_repository_factory is None
            or self._numbering_service is None
        ):
            raise ValidationError(
                "Tax payment journal posting is not wired in this context."
            )

        tax_type = tax_return.tax_type_code
        if tax_type == TAX_TYPE_VAT:
            debit_account_code = SETTLEMENT_VAT_PAYABLE_ACCOUNT_CODE
            requires_settlement = True
            description_prefix = "VAT"
        elif tax_type in ALL_ASSESSED_RETURN_TAX_TYPES:
            debit_account_code = ASSESSED_PAYMENT_DEBIT_ACCOUNT_CODE_BY_TAX_TYPE[
                tax_type
            ]
            requires_settlement = False
            description_prefix = tax_type
        else:
            raise ValidationError(
                f"Bank-side journal posting is not supported for tax type "
                f"{tax_type}."
            )

        if requires_settlement and tax_return.journal_entry_id is None:
            raise ValidationError(
                "The tax return must be settled (have a settlement journal) "
                "before payments can be posted against it."
            )

        account_repo = self._account_repository_factory(session)
        treasury_account = account_repo.get_by_id(company_id, treasury_account_id)
        if treasury_account is None:
            raise NotFoundError(
                f"Treasury account {treasury_account_id} was not found."
            )
        if not treasury_account.is_active:
            raise ValidationError(
                f"Treasury account {treasury_account.account_code} is not active."
            )
        if not treasury_account.allow_manual_posting:
            raise ValidationError(
                f"Treasury account {treasury_account.account_code} does not "
                "allow manual posting."
            )

        payable_account = account_repo.get_by_code(
            company_id, debit_account_code
        )
        if payable_account is None:
            raise ValidationError(
                f"Debit account {debit_account_code} for {tax_type} "
                "is not configured in the chart of accounts."
            )
        if not payable_account.allow_manual_posting:
            raise ValidationError(
                f"Debit account {payable_account.account_code} does "
                "not allow manual posting."
            )

        period_repo = self._fiscal_period_repository_factory(session)
        fiscal_period = period_repo.get_covering_date(company_id, payment_date)
        if fiscal_period is None:
            raise ValidationError(
                "Payment date must fall within an existing fiscal period."
            )
        if fiscal_period.status_code == "LOCKED":
            raise PeriodLockedError(
                f"Tax payment cannot be posted into locked fiscal period "
                f"{fiscal_period.period_code}."
            )
        if fiscal_period.status_code != "OPEN":
            raise ValidationError(
                "Tax payment can only be posted into an open fiscal period."
            )

        journal_repo = self._journal_entry_repository_factory(session)
        description = (
            f"{description_prefix} payment {payment_date.isoformat()} via {method} "
            f"(return {tax_return.id})"
        )
        journal_entry = JournalEntry(
            company_id=company_id,
            fiscal_period_id=fiscal_period.id,
            entry_number=None,
            entry_date=payment_date,
            transaction_date=payment_date,
            journal_type_code=_JOURNAL_TYPE_CODE_OD,
            reference_text=(
                reference
                or f"{description_prefix}-PAY-{tax_return.id}"
            )[:120],
            description=description,
            source_module_code="taxation",
            source_document_type="tax_payment",
            source_document_id=None,  # stamped after payment.id is known via flush below
            status_code="POSTED",
            posted_at=datetime.utcnow(),
            posted_by_user_id=actor_id,
            created_by_user_id=actor_id,
        )
        journal_repo.add(journal_entry)
        # Flush so payment.id (and je.id) become available.
        session.flush()
        journal_entry.entry_number = self._numbering_service.issue_next_number(
            session,
            company_id=company_id,
            document_type_code=_JOURNAL_DOC_TYPE,
        )
        if payment.id is not None:
            journal_entry.source_document_id = payment.id
        journal_repo.save(journal_entry)

        # Lines: Dr <type-specific account> / Cr treasury.
        session.add(
            JournalEntryLine(
                journal_entry_id=journal_entry.id,
                line_number=1,
                account_id=payable_account.id,
                line_description=f"{description_prefix} settlement ({method})",
                debit_amount=amount,
                credit_amount=_ZERO,
            )
        )
        session.add(
            JournalEntryLine(
                journal_entry_id=journal_entry.id,
                line_number=2,
                account_id=treasury_account.id,
                line_description=(
                    f"{description_prefix} payment via {method}"
                    + (f" — {reference}" if reference else "")
                ),
                debit_amount=_ZERO,
                credit_amount=amount,
            )
        )
        session.flush()
        return journal_entry.id

    def _require_company_exists(self, session: Session, company_id: int) -> None:
        company_repo = self._company_repository_factory(session)
        if company_repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

    @staticmethod
    def _to_dto(p: TaxPayment) -> TaxPaymentDTO:
        return TaxPaymentDTO(
            id=p.id,
            company_id=p.company_id,
            tax_return_id=p.tax_return_id,
            payment_date=p.payment_date,
            amount=p.amount,
            payment_method_code=p.payment_method_code,
            reference=p.reference,
            notes=p.notes,
            journal_entry_id=p.journal_entry_id,
            recorded_by_user_id=p.recorded_by_user_id,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )

    def _record_audit(
        self,
        company_id: int,
        entity_id: int | None,
        description: str,
        *,
        event_type_code: str = "TAX_PAYMENT_RECORDED",
    ) -> None:
        if self._audit_service is None:
            return
        from seeker_accounting.modules.audit.dto.audit_event_dto import (
            RecordAuditEventCommand,
        )
        from seeker_accounting.modules.audit.event_type_catalog import MODULE_TAXATION

        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type_code,
                    module_code=MODULE_TAXATION,
                    entity_type="TaxPayment",
                    entity_id=entity_id,
                    description=description,
                ),
            )
        except Exception:
            pass
