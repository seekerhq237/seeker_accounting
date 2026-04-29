"""FxRevaluationService — books a single FX revaluation journal entry.

For each line, the service computes the adjustment needed to move the account's
local-currency carrying amount from `current_book_amount` to `target_amount`.

Per-line adjustment delta = target_amount - current_book_amount

  delta > 0  → DR account / CR offset (gain or loss, see below)
  delta < 0  → CR account / DR offset

The offset side aggregates all per-line deltas. The total net is then booked
in one or two summary lines against the gain or loss account based on direction.

A single balanced JE is written:
  - one line per revalued account (the per-line delta)
  - one or two summary lines posting the total to gain/loss

Sign convention of `current_book_amount` and `target_amount`:
  positive = the account currently/should carry a debit-side balance
  negative = the account currently/should carry a credit-side balance
The math (delta = target - current) works for both cases.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.app.context.app_context import AppContext
from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.accounting.fiscal_periods.repositories.fiscal_period_repository import (
    FiscalPeriodRepository,
)
from seeker_accounting.modules.accounting.journals.dto.fx_revaluation_dto import (
    FxRevaluationCommand,
    FxRevaluationResultDTO,
)
from seeker_accounting.modules.accounting.journals.models.journal_entry import JournalEntry
from seeker_accounting.modules.accounting.journals.models.journal_entry_line import (
    JournalEntryLine,
)
from seeker_accounting.modules.audit.event_type_catalog import FX_REVALUATION_POSTED
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.platform.exceptions import (
    ConflictError,
    NotFoundError,
    PeriodLockedError,
    ValidationError,
)
from seeker_accounting.platform.numbering.numbering_service import NumberingService

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

_ZERO = Decimal("0")
_ONE_MICRO = Decimal("0.000001")

FiscalPeriodRepositoryFactory = Callable[[Session], FiscalPeriodRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]


class FxRevaluationService:
    SOURCE_MODULE_CODE = "ACCOUNTING"
    SOURCE_DOCUMENT_TYPE = "FX_REVALUATION"
    JOURNAL_TYPE_CODE = "FX_REVALUATION"

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        app_context: AppContext,
        fiscal_period_repository_factory: FiscalPeriodRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        numbering_service: NumberingService,
        audit_service: "AuditService | None" = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._app_context = app_context
        self._fiscal_period_repository_factory = fiscal_period_repository_factory
        self._company_repository_factory = company_repository_factory
        self._numbering_service = numbering_service
        self._audit_service = audit_service

    def post_revaluation(
        self,
        company_id: int,
        command: FxRevaluationCommand,
        actor_user_id: int | None = None,
    ) -> FxRevaluationResultDTO:
        if not command.lines:
            raise ValidationError("At least one revaluation line is required.")
        if command.gain_account_id == command.loss_account_id:
            raise ValidationError("Gain and loss accounts must be different.")

        # Compute per-line deltas and validate at least one is non-zero.
        deltas: list[tuple[int, Decimal, str | None]] = []
        for ln in command.lines:
            delta = Decimal(ln.target_amount) - Decimal(ln.current_book_amount)
            if delta.copy_abs() <= _ONE_MICRO:
                continue
            deltas.append((ln.account_id, delta, ln.description))
        if not deltas:
            raise ValidationError(
                "All revaluation lines have zero adjustment — nothing to post."
            )

        seen_accounts: set[int] = set()
        for account_id, _, _ in deltas:
            if account_id in seen_accounts:
                raise ValidationError(
                    f"Account {account_id} appears more than once with a non-zero delta."
                )
            seen_accounts.add(account_id)
        if command.gain_account_id in seen_accounts or command.loss_account_id in seen_accounts:
            raise ValidationError(
                "Gain/loss accounts cannot also appear as revalued lines."
            )

        with self._unit_of_work_factory() as uow:
            actor_id = (
                actor_user_id
                if actor_user_id is not None
                else self._app_context.current_user_id
            )
            self._require_company(uow.session, company_id)

            fp_repo = self._fiscal_period_repository_factory(uow.session)
            period = fp_repo.get_covering_date(company_id, command.revaluation_date)
            if period is None:
                raise ValidationError(
                    "Revaluation date must fall within an existing fiscal period."
                )
            if period.status_code == "LOCKED":
                raise PeriodLockedError("Cannot post into a locked fiscal period.")
            if period.status_code != "OPEN":
                raise ValidationError("Can only post into an open fiscal period.")

            entry_number = self._numbering_service.issue_next_number(
                uow.session,
                company_id=company_id,
                document_type_code="JOURNAL_ENTRY",
            )
            description = "FX revaluation"
            if command.reference:
                description = f"FX revaluation — {command.reference}"
            now = datetime.utcnow()
            journal_entry = JournalEntry(
                company_id=company_id,
                fiscal_period_id=period.id,
                entry_date=command.revaluation_date,
                journal_type_code=self.JOURNAL_TYPE_CODE,
                description=description,
                source_module_code=self.SOURCE_MODULE_CODE,
                source_document_type=self.SOURCE_DOCUMENT_TYPE,
                source_document_id=None,
                status_code="POSTED",
                posted_at=now,
                posted_by_user_id=actor_id,
                entry_number=entry_number,
                reference_text=command.reference,
            )
            uow.session.add(journal_entry)
            uow.session.flush()

            line_no = 1
            lines_to_add: list[JournalEntryLine] = []
            total_dr = _ZERO
            total_cr = _ZERO
            total_gain = _ZERO
            total_loss = _ZERO

            for account_id, delta, line_description in deltas:
                if delta > _ZERO:
                    debit, credit = delta, _ZERO
                    total_gain += delta
                else:
                    debit, credit = _ZERO, -delta
                    total_loss += -delta
                lines_to_add.append(
                    JournalEntryLine(
                        journal_entry_id=journal_entry.id,
                        line_number=line_no,
                        account_id=account_id,
                        debit_amount=debit,
                        credit_amount=credit,
                        line_description=line_description or "FX revaluation adjustment",
                    )
                )
                total_dr += debit
                total_cr += credit
                line_no += 1

            # Net adjustment: total_gain (DR side accumulated on revalued accounts)
            # - total_loss (CR side). If positive, it's a net unrealized gain → CR gain.
            # If negative, it's a net unrealized loss → DR loss.
            net = total_gain - total_loss
            if net.copy_abs() > _ONE_MICRO:
                if net > _ZERO:
                    lines_to_add.append(
                        JournalEntryLine(
                            journal_entry_id=journal_entry.id,
                            line_number=line_no,
                            account_id=command.gain_account_id,
                            debit_amount=_ZERO,
                            credit_amount=net,
                            line_description="Net unrealized FX gain",
                        )
                    )
                    total_cr += net
                else:
                    lines_to_add.append(
                        JournalEntryLine(
                            journal_entry_id=journal_entry.id,
                            line_number=line_no,
                            account_id=command.loss_account_id,
                            debit_amount=-net,
                            credit_amount=_ZERO,
                            line_description="Net unrealized FX loss",
                        )
                    )
                    total_dr += -net
                line_no += 1

            for line_obj in lines_to_add:
                uow.session.add(line_obj)
            uow.session.flush()

            if (total_dr - total_cr).copy_abs() > _ONE_MICRO:
                raise ValidationError(
                    f"FX revaluation journal is unbalanced: DR={total_dr} CR={total_cr}."
                )

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ConflictError("FX revaluation failed due to a data conflict.") from exc

            self._record_audit(
                company_id,
                journal_entry.id,
                f"FX revaluation posted: {len(deltas)} accounts, "
                f"gain={total_gain}, loss={total_loss}, net={net}.",
            )

            return FxRevaluationResultDTO(
                journal_entry_id=journal_entry.id,
                journal_entry_number=entry_number,
                revaluation_date=command.revaluation_date,
                total_gain=total_gain,
                total_loss=total_loss,
                net_adjustment=net,
                line_count=len(deltas),
                posted_at=now,
            )

    def _require_company(self, session: Session, company_id: int) -> None:
        repo = self._company_repository_factory(session)
        if repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company {company_id} not found.")

    def _record_audit(
        self,
        company_id: int,
        journal_entry_id: int,
        detail: str,
    ) -> None:
        if self._audit_service is None:
            return
        from seeker_accounting.modules.audit.dto.audit_event_dto import (
            RecordAuditEventCommand,
        )
        from seeker_accounting.modules.audit.event_type_catalog import MODULE_JOURNALS

        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=FX_REVALUATION_POSTED,
                    module_code=MODULE_JOURNALS,
                    entity_type="JournalEntry",
                    entity_id=journal_entry_id,
                    description=detail,
                ),
            )
        except Exception:
            pass
