"""PayrollPostingService — post an approved payroll run to the GL.

One payroll run → one posted journal entry.
Posting is idempotent: attempting to post an already-posted run raises ValidationError.

Journal construction:
  - Dr: expense accounts (grouped by account, earning + employer contribution expense)
  - Cr: liability accounts (grouped by account, deductions + taxes + employer contributions)
  - Cr: payroll_payable role account (total net payable across all included employees)

Immutability:
  - Once posted, the run cannot be recalculated or voided.
  - Settlement tracking (payments, remittances) may still proceed.

Does NOT auto-create payment or remittance records.
"""

from __future__ import annotations

from collections import defaultdict
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Callable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.app.context.app_context import AppContext
from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.accounting.chart_of_accounts.repositories.account_repository import (
    AccountRepository,
)
from seeker_accounting.modules.accounting.fiscal_periods.repositories.fiscal_period_repository import (
    FiscalPeriodRepository,
)
from seeker_accounting.modules.accounting.journals.models.journal_entry import JournalEntry
from seeker_accounting.modules.accounting.journals.models.journal_entry_line import (
    JournalEntryLine,
)
from seeker_accounting.modules.accounting.journals.repositories.journal_entry_repository import (
    JournalEntryRepository,
)
from seeker_accounting.modules.accounting.reference_data.repositories.account_role_mapping_repository import (
    AccountRoleMappingRepository,
)
from seeker_accounting.modules.audit.dto.audit_event_dto import RecordAuditEventCommand
from seeker_accounting.modules.audit.services.audit_service import AuditService
from seeker_accounting.modules.payroll.dto.payroll_posting_dto import (
    PostPayrollRunCommand,
    PostingJournalLineDTO,
    PayrollPostingResultDTO,
    PayrollReversalResultDTO,
    ReversePayrollRunCommand,
)
from seeker_accounting.modules.payroll.payroll_permissions import PAYROLL_RUN_POST
from seeker_accounting.modules.payroll.models.payroll_component import PayrollComponent
from seeker_accounting.modules.payroll.models.payroll_run import PayrollRun
from seeker_accounting.modules.payroll.models.payroll_run_employee import PayrollRunEmployee
from seeker_accounting.modules.payroll.models.payroll_run_line import PayrollRunLine
from seeker_accounting.modules.payroll.repositories.payroll_run_repository import (
    PayrollRunRepository,
)
from seeker_accounting.platform.exceptions import (
    NotFoundError,
    PeriodLockedError,
    ValidationError,
)
from seeker_accounting.platform.numbering.numbering_service import NumberingService
from seeker_accounting.shared.services.telemetry_service import TelemetryService

_PAYROLL_PAYABLE_ROLE = "payroll_payable"
_JOURNAL_DOC_TYPE = "journal_entry"
_DEBIT_TYPES = frozenset({"earning", "employer_contribution"})
_CREDIT_TYPES = frozenset({"deduction", "tax", "employer_contribution"})

_CALENDAR_MONTHS = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December",
}


class PayrollPostingService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        app_context: AppContext,
        run_repository_factory: Callable[[Session], PayrollRunRepository],
        journal_entry_repository_factory: Callable[[Session], JournalEntryRepository],
        account_repository_factory: Callable[[Session], AccountRepository],
        fiscal_period_repository_factory: Callable[[Session], FiscalPeriodRepository],
        account_role_mapping_repository_factory: Callable[
            [Session], AccountRoleMappingRepository
        ],
        numbering_service: NumberingService,
        permission_service: PermissionService,
        audit_service: AuditService,
        telemetry_service: TelemetryService | None = None,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._app_context = app_context
        self._run_repo_factory = run_repository_factory
        self._journal_repo_factory = journal_entry_repository_factory
        self._account_repo_factory = account_repository_factory
        self._period_repo_factory = fiscal_period_repository_factory
        self._role_mapping_repo_factory = account_role_mapping_repository_factory
        self._numbering_service = numbering_service
        self._permission_service = permission_service
        self._audit_service = audit_service
        self._telemetry = telemetry_service

    def post_run(
        self,
        company_id: int,
        cmd: PostPayrollRunCommand,
        actor_user_id: int | None = None,
    ) -> PayrollPostingResultDTO:
        """Post one payroll run to the GL.  Creates one balanced journal entry."""
        self._permission_service.require_permission(PAYROLL_RUN_POST)
        actor_id = actor_user_id or self._app_context.current_user_id

        with self._uow_factory() as uow:
            run_repo = self._run_repo_factory(uow.session)
            run = run_repo.get_by_id(company_id, cmd.run_id)
            if run is None:
                raise NotFoundError("Payroll run not found.")
            if run.status_code == "posted":
                raise ValidationError("This payroll run has already been posted.")
            if run.status_code not in ("approved", "calculated"):
                raise ValidationError(
                    f"Run status is '{run.status_code}'. Only approved or calculated runs can be posted."
                )

            # Load included employees with their lines and component accounts
            employees = self._load_included_employees(
                uow.session, company_id, cmd.run_id
            )
            if not employees:
                raise ValidationError(
                    "No included employees in this run. Nothing to post."
                )

            # Fiscal period
            period_repo = self._period_repo_factory(uow.session)
            fiscal_period = period_repo.get_covering_date(company_id, cmd.posting_date)
            if fiscal_period is None:
                raise ValidationError(
                    f"No fiscal period covers the posting date {cmd.posting_date}."
                )
            if fiscal_period.status_code == "LOCKED":
                raise PeriodLockedError(
                    f"Fiscal period '{fiscal_period.period_code}' is locked."
                )
            if fiscal_period.status_code != "OPEN":
                raise ValidationError(
                    f"Fiscal period '{fiscal_period.period_code}' is not open for posting."
                )

            # Payroll payable account (credit side for net pay)
            role_repo = self._role_mapping_repo_factory(uow.session)
            payroll_payable_mapping = role_repo.get_by_role_code(
                company_id, _PAYROLL_PAYABLE_ROLE
            )
            if payroll_payable_mapping is None:
                raise ValidationError(
                    "The 'Payroll Payable' account role is not mapped. "
                    "Configure it in Accounting Setup before posting."
                )
            acct_repo = self._account_repo_factory(uow.session)
            payroll_payable_acct = acct_repo.get_by_id(
                company_id, payroll_payable_mapping.account_id
            )
            if payroll_payable_acct is None or not payroll_payable_acct.is_active:
                raise ValidationError("The mapped 'Payroll Payable' account is not active.")
            if not payroll_payable_acct.allow_manual_posting:
                raise ValidationError(
                    "The mapped 'Payroll Payable' account does not allow posting."
                )

            # Build journal lines from run employee lines
            debit_by_account: dict[int, Decimal] = defaultdict(Decimal)
            credit_by_account: dict[int, Decimal] = defaultdict(Decimal)
            total_net_payable = Decimal("0")

            # Load all components used in this run
            component_ids = {
                line.component_id
                for emp in employees
                for line in emp.lines
                if line.component_type_code != "informational"
            }
            comp_stmt = select(PayrollComponent).where(
                PayrollComponent.id.in_(component_ids),
                PayrollComponent.company_id == company_id,
            )
            components_by_id = {
                c.id: c
                for c in uow.session.scalars(comp_stmt).all()
            }

            for emp in employees:
                total_net_payable += Decimal(str(emp.net_payable))
                for line in emp.lines:
                    if line.component_type_code == "informational":
                        continue
                    comp = components_by_id.get(line.component_id)
                    if comp is None:
                        raise ValidationError(
                            f"Component id={line.component_id} not found. Run validation first."
                        )
                    amount = Decimal(str(line.component_amount))
                    if amount == Decimal("0"):
                        continue

                    if line.component_type_code in _DEBIT_TYPES:
                        if comp.expense_account_id is None:
                            raise ValidationError(
                                f"Component '{comp.component_code}' has no expense account. "
                                "Run validation before posting."
                            )
                        debit_by_account[comp.expense_account_id] += amount

                    if line.component_type_code in _CREDIT_TYPES:
                        if comp.liability_account_id is None:
                            raise ValidationError(
                                f"Component '{comp.component_code}' has no liability account. "
                                "Run validation before posting."
                            )
                        credit_by_account[comp.liability_account_id] += amount

            # Credit net salary payable
            if total_net_payable > Decimal("0"):
                credit_by_account[payroll_payable_acct.id] += total_net_payable

            # Verify balance
            total_debit = sum(debit_by_account.values(), Decimal("0"))
            total_credit = sum(credit_by_account.values(), Decimal("0"))
            if abs(total_debit - total_credit) > Decimal("0.01"):
                raise ValidationError(
                    f"Payroll journal does not balance: "
                    f"Dr={total_debit:.2f} Cr={total_credit:.2f}. "
                    f"Difference: {total_debit - total_credit:.2f}"
                )

            # Validate all debit/credit accounts
            all_account_ids = set(debit_by_account) | set(credit_by_account)
            accounts_by_id = {}
            for aid in all_account_ids:
                acct = acct_repo.get_by_id(company_id, aid)
                if acct is None:
                    raise ValidationError(f"Account id={aid} not found.")
                if not acct.is_active:
                    raise ValidationError(f"Account '{acct.account_code}' is inactive.")
                if not acct.allow_manual_posting:
                    raise ValidationError(
                        f"Account '{acct.account_code}' does not allow posting."
                    )
                accounts_by_id[aid] = acct

            period_label = f"{_CALENDAR_MONTHS[run.period_month]} {run.period_year}"
            narration = cmd.narration or f"Payroll — {period_label} ({run.run_reference})"

            # Build journal entry
            journal_repo = self._journal_repo_factory(uow.session)
            journal_entry = JournalEntry(
                company_id=company_id,
                fiscal_period_id=fiscal_period.id,
                entry_date=cmd.posting_date,
                journal_type_code="PAYROLL",
                reference_text=run.run_reference,
                description=narration,
                source_module_code="PAYROLL",
                source_document_type="PAYROLL_RUN",
                source_document_id=run.id,
                status_code="DRAFT",
                created_by_user_id=actor_id,
            )
            journal_repo.add(journal_entry)
            uow.session.flush()

            built_lines: list[JournalEntryLine] = []
            line_num = 1
            for acct_id, debit_amt in sorted(debit_by_account.items()):
                acct = accounts_by_id[acct_id]
                built_lines.append(
                    JournalEntryLine(
                        journal_entry_id=journal_entry.id,
                        line_number=line_num,
                        account_id=acct_id,
                        line_description=f"{narration} — {acct.account_name}",
                        debit_amount=debit_amt.quantize(Decimal("0.01")),
                        credit_amount=Decimal("0.00"),
                    )
                )
                line_num += 1

            for acct_id, credit_amt in sorted(credit_by_account.items()):
                acct = accounts_by_id[acct_id]
                built_lines.append(
                    JournalEntryLine(
                        journal_entry_id=journal_entry.id,
                        line_number=line_num,
                        account_id=acct_id,
                        line_description=f"{narration} — {acct.account_name}",
                        debit_amount=Decimal("0.00"),
                        credit_amount=credit_amt.quantize(Decimal("0.01")),
                    )
                )
                line_num += 1

            for ln in built_lines:
                uow.session.add(ln)
            uow.session.flush()

            # Issue journal number and mark posted
            entry_number = self._numbering_service.issue_next_number(
                uow.session, company_id, _JOURNAL_DOC_TYPE
            )
            journal_entry.entry_number = entry_number
            now = datetime.now(timezone.utc)
            journal_entry.status_code = "POSTED"
            journal_entry.posted_at = now
            journal_entry.posted_by_user_id = actor_id

            # Mark payroll run as posted
            previous_run_status = run.status_code
            run.status_code = "posted"
            run.posted_at = now
            run.posted_by_user_id = actor_id
            run.posted_journal_entry_id = journal_entry.id

            self._record_state_transition_in_session(
                uow.session,
                company_id,
                run,
                from_state=previous_run_status,
                to_state="posted",
                description=f"Posted payroll run '{run.run_reference}' to journal '{entry_number}'.",
                context={
                    "journal_entry_id": journal_entry.id,
                    "entry_number": entry_number,
                    "posting_date": cmd.posting_date.isoformat(),
                },
            )

            self._audit_service.record_event_in_session(
                uow.session,
                company_id,
                RecordAuditEventCommand(
                    event_type_code="PAYROLL_RUN_POSTED",
                    module_code="payroll",
                    entity_type="payroll_run",
                    entity_id=run.id,
                    description=(
                        f"Posted payroll run '{run.run_reference}' to journal '{entry_number}'."
                    ),
                    detail_json=json.dumps(
                        {
                            "run_reference": run.run_reference,
                            "journal_entry_id": journal_entry.id,
                            "entry_number": entry_number,
                            "posting_date": cmd.posting_date.isoformat(),
                            "total_debit": str(total_debit.quantize(Decimal("0.01"))),
                            "total_credit": str(total_credit.quantize(Decimal("0.01"))),
                        }
                    ),
                ),
            )

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError(
                    "Payroll journal could not be saved. Check for duplicate journal numbers."
                ) from exc

            if self._telemetry is not None:
                self._telemetry.record_funnel_step(
                    funnel="monthly_run",
                    step="run_posted",
                    event_code="monthly_run.run_posted",
                    context={
                        "company_id": company_id,
                        "period_year": run.period_year,
                        "period_month": run.period_month,
                    },
                )

            # Build result DTO
            journal_line_dtos = tuple(
                PostingJournalLineDTO(
                    account_id=ln.account_id,
                    account_code=accounts_by_id[ln.account_id].account_code,
                    account_name=accounts_by_id[ln.account_id].account_name,
                    line_description=ln.line_description or "",
                    debit_amount=ln.debit_amount,
                    credit_amount=ln.credit_amount,
                )
                for ln in sorted(built_lines, key=lambda x: x.line_number)
            )
            return PayrollPostingResultDTO(
                run_id=run.id,
                run_reference=run.run_reference,
                journal_entry_id=journal_entry.id,
                entry_number=entry_number,
                posting_date=cmd.posting_date,
                total_debit=total_debit.quantize(Decimal("0.01")),
                total_credit=total_credit.quantize(Decimal("0.01")),
                posted_at=now,
                journal_lines=journal_line_dtos,
            )

    def _load_included_employees(
        self, session: Session, company_id: int, run_id: int
    ) -> list[PayrollRunEmployee]:
        stmt = (
            select(PayrollRunEmployee)
            .where(
                PayrollRunEmployee.company_id == company_id,
                PayrollRunEmployee.run_id == run_id,
                PayrollRunEmployee.status_code == "included",
            )
            .options(
                selectinload(PayrollRunEmployee.lines),
            )
        )
        return list(session.scalars(stmt).all())

    # ── Reversal ──────────────────────────────────────────────────────────────

    def reverse_run(
        self,
        company_id: int,
        cmd: ReversePayrollRunCommand,
        actor_user_id: int | None = None,
    ) -> PayrollReversalResultDTO:
        """Create an offsetting journal entry against a posted payroll run.

        After reversal the run's GL effect is fully neutralised. The run
        moves to the terminal ``reversed`` status. Settlement records
        (payments, remittances) remain visible for audit but should not be
        treated as live obligations.
        """
        self._permission_service.require_permission(PAYROLL_RUN_POST)
        actor_id = actor_user_id or self._app_context.current_user_id
        reason = (cmd.reason or "").strip()
        if not reason:
            raise ValidationError("A reason is required to reverse a posted payroll run.")

        with self._uow_factory() as uow:
            run_repo = self._run_repo_factory(uow.session)
            run = run_repo.get_by_id(company_id, cmd.run_id)
            if run is None:
                raise NotFoundError("Payroll run not found.")
            if run.status_code != "posted":
                raise ValidationError(
                    f"Only posted runs can be reversed (current status: '{run.status_code}')."
                )
            if run.posted_journal_entry_id is None:
                raise ValidationError(
                    "Posted run is missing its source journal entry; cannot reverse."
                )
            if run.reversal_journal_entry_id is not None:
                raise ValidationError("This payroll run has already been reversed.")

            # Period covering reversal date must be open
            period_repo = self._period_repo_factory(uow.session)
            fiscal_period = period_repo.get_covering_date(company_id, cmd.reversal_date)
            if fiscal_period is None:
                raise ValidationError(
                    f"No fiscal period covers the reversal date {cmd.reversal_date}."
                )
            if fiscal_period.status_code == "LOCKED":
                raise PeriodLockedError(
                    f"Fiscal period '{fiscal_period.period_code}' is locked."
                )
            if fiscal_period.status_code != "OPEN":
                raise ValidationError(
                    f"Fiscal period '{fiscal_period.period_code}' is not open for posting."
                )

            # Load original journal entry lines
            from seeker_accounting.modules.accounting.journals.models.journal_entry import (
                JournalEntry as _JE,
            )
            from seeker_accounting.modules.accounting.journals.models.journal_entry_line import (
                JournalEntryLine as _JEL,
            )
            original = uow.session.get(_JE, run.posted_journal_entry_id)
            if original is None:
                raise ValidationError("Original posted journal entry not found.")
            original_lines = list(
                uow.session.scalars(
                    select(_JEL)
                    .where(_JEL.journal_entry_id == original.id)
                    .order_by(_JEL.line_number)
                )
            )
            if not original_lines:
                raise ValidationError("Original posted journal entry has no lines to reverse.")

            # Verify accounts on the offsetting entry are still postable
            acct_repo = self._account_repo_factory(uow.session)
            account_ids = {ln.account_id for ln in original_lines}
            accounts_by_id = {}
            for aid in account_ids:
                acct = acct_repo.get_by_id(company_id, aid)
                if acct is None:
                    raise ValidationError(f"Account id={aid} not found.")
                if not acct.is_active:
                    raise ValidationError(
                        f"Account '{acct.account_code}' is inactive — cannot post reversal."
                    )
                if not acct.allow_manual_posting:
                    raise ValidationError(
                        f"Account '{acct.account_code}' does not allow posting."
                    )
                accounts_by_id[aid] = acct

            period_label = f"{_CALENDAR_MONTHS[run.period_month]} {run.period_year}"
            narration = cmd.narration or (
                f"REVERSAL — Payroll {period_label} ({run.run_reference}): {reason}"
            )

            # Build reversal journal entry — debits and credits swapped
            journal_repo = self._journal_repo_factory(uow.session)
            reversal_entry = JournalEntry(
                company_id=company_id,
                fiscal_period_id=fiscal_period.id,
                entry_date=cmd.reversal_date,
                journal_type_code="PAYROLL",
                reference_text=f"REV-{run.run_reference}",
                description=narration,
                source_module_code="PAYROLL",
                source_document_type="PAYROLL_RUN_REVERSAL",
                source_document_id=run.id,
                status_code="DRAFT",
                created_by_user_id=actor_id,
            )
            journal_repo.add(reversal_entry)
            uow.session.flush()

            built_lines: list[JournalEntryLine] = []
            total_debit = Decimal("0")
            total_credit = Decimal("0")
            for idx, src in enumerate(original_lines, start=1):
                acct = accounts_by_id[src.account_id]
                # Swap debit/credit to neutralise the original entry
                new_debit = Decimal(str(src.credit_amount)).quantize(Decimal("0.01"))
                new_credit = Decimal(str(src.debit_amount)).quantize(Decimal("0.01"))
                total_debit += new_debit
                total_credit += new_credit
                built_lines.append(
                    JournalEntryLine(
                        journal_entry_id=reversal_entry.id,
                        line_number=idx,
                        account_id=src.account_id,
                        line_description=f"{narration} — {acct.account_name}",
                        debit_amount=new_debit,
                        credit_amount=new_credit,
                    )
                )
            for ln in built_lines:
                uow.session.add(ln)
            uow.session.flush()

            if abs(total_debit - total_credit) > Decimal("0.01"):
                raise ValidationError(
                    f"Reversal journal does not balance: "
                    f"Dr={total_debit:.2f} Cr={total_credit:.2f}."
                )

            entry_number = self._numbering_service.issue_next_number(
                uow.session, company_id, _JOURNAL_DOC_TYPE
            )
            reversal_entry.entry_number = entry_number
            now = datetime.now(timezone.utc)
            reversal_entry.status_code = "POSTED"
            reversal_entry.posted_at = now
            reversal_entry.posted_by_user_id = actor_id

            previous_run_status = run.status_code
            run.status_code = "reversed"
            run.reversed_at = now
            run.reversed_by_user_id = actor_id
            run.reversal_journal_entry_id = reversal_entry.id
            run.reversal_reason = reason

            self._record_state_transition_in_session(
                uow.session,
                company_id,
                run,
                from_state=previous_run_status,
                to_state="reversed",
                description=f"Reversed payroll run '{run.run_reference}' via journal '{entry_number}'.",
                reason=reason,
                context={
                    "original_journal_entry_id": original.id,
                    "reversal_journal_entry_id": reversal_entry.id,
                    "reversal_entry_number": entry_number,
                    "reversal_date": cmd.reversal_date.isoformat(),
                },
            )

            self._audit_service.record_event_in_session(
                uow.session,
                company_id,
                RecordAuditEventCommand(
                    event_type_code="PAYROLL_RUN_REVERSED",
                    module_code="payroll",
                    entity_type="payroll_run",
                    entity_id=run.id,
                    description=(
                        f"Reversed payroll run '{run.run_reference}' via journal '{entry_number}'."
                    ),
                    detail_json=json.dumps(
                        {
                            "run_reference": run.run_reference,
                            "original_journal_entry_id": original.id,
                            "reversal_journal_entry_id": reversal_entry.id,
                            "reversal_entry_number": entry_number,
                            "reversal_date": cmd.reversal_date.isoformat(),
                            "reason": reason,
                            "total_debit": str(total_debit.quantize(Decimal("0.01"))),
                            "total_credit": str(total_credit.quantize(Decimal("0.01"))),
                        }
                    ),
                ),
            )

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError(
                    "Reversal journal could not be saved. Check for duplicate journal numbers."
                ) from exc

            if self._telemetry is not None:
                self._telemetry.record_funnel_step(
                    funnel="monthly_run",
                    step="run_reversed",
                    event_code="monthly_run.run_reversed",
                    context={
                        "company_id": company_id,
                        "period_year": run.period_year,
                        "period_month": run.period_month,
                    },
                )

            journal_line_dtos = tuple(
                PostingJournalLineDTO(
                    account_id=ln.account_id,
                    account_code=accounts_by_id[ln.account_id].account_code,
                    account_name=accounts_by_id[ln.account_id].account_name,
                    line_description=ln.line_description or "",
                    debit_amount=ln.debit_amount,
                    credit_amount=ln.credit_amount,
                )
                for ln in sorted(built_lines, key=lambda x: x.line_number)
            )
            return PayrollReversalResultDTO(
                run_id=run.id,
                run_reference=run.run_reference,
                original_journal_entry_id=original.id,
                reversal_journal_entry_id=reversal_entry.id,
                reversal_entry_number=entry_number,
                reversal_date=cmd.reversal_date,
                total_debit=total_debit.quantize(Decimal("0.01")),
                total_credit=total_credit.quantize(Decimal("0.01")),
                reversed_at=now,
                journal_lines=journal_line_dtos,
            )

    def _record_state_transition_in_session(
        self,
        session: Session,
        company_id: int,
        run: PayrollRun,
        *,
        from_state: str | None,
        to_state: str,
        description: str,
        reason: str | None = None,
        context: dict[str, object] | None = None,
    ) -> None:
        recorder = getattr(self._audit_service, "record_state_transition_in_session", None)
        if recorder is None:
            return
        recorder(
            session,
            company_id,
            module_code="payroll",
            entity_type="payroll_run",
            entity_id=run.id,
            from_state=from_state,
            to_state=to_state,
            description=description,
            reason=reason,
            context={"run_reference": run.run_reference, **(context or {})},
        )
