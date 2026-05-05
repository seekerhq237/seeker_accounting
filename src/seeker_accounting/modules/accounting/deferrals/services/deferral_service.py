"""Deferral Service — manages prepaid expenses and unearned revenue schedules.

Accounting rules:
  EXPENSE deferral (charges constatées d'avance, OHADA 476):
    On creation/activation:  nothing — the initial booking (Dr 476, Cr AP/Cash)
                             is on the source document (bill / payment).
    On recognition posting:  Dr recognition_account (expense)
                             Cr holding_account (476)

  REVENUE deferral (produits constatés d'avance, OHADA 477):
    On creation/activation:  nothing — the initial booking (Dr Cash/AR, Cr 477)
                             is on the source document (invoice / receipt).
    On recognition posting:  Dr holding_account (477)
                             Cr recognition_account (revenue)

Posting creates a POSTED JournalEntry with two balanced lines and stamps
the DeferralScheduleLine.journal_entry_id.

When all lines on a schedule are POSTED, the schedule status advances
automatically to COMPLETE.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.accounting.deferrals.dto.deferral_dto import (
    ActivateDeferralScheduleCommand,
    CancelDeferralScheduleCommand,
    CreateDeferralScheduleCommand,
    DeferralLineDTO,
    DeferralScheduleDTO,
    PostAllDueCommand,
    PostRecognitionLineCommand,
)
from seeker_accounting.modules.accounting.deferrals.models.deferral_schedule import (
    DEFERRAL_STATUS_ACTIVE,
    DEFERRAL_STATUS_CANCELLED,
    DEFERRAL_STATUS_COMPLETE,
    DEFERRAL_STATUS_DRAFT,
    DEFERRAL_TYPE_EXPENSE,
    DEFERRAL_TYPE_REVENUE,
    LINE_STATUS_PENDING,
    LINE_STATUS_POSTED,
    DeferralSchedule,
    DeferralScheduleLine,
)
from seeker_accounting.modules.accounting.deferrals.repositories.deferral_repository import (
    DeferralRepository,
)
from seeker_accounting.modules.accounting.fiscal_periods.repositories.fiscal_period_repository import (
    FiscalPeriodRepository,
)
from seeker_accounting.modules.accounting.journals.models.journal_entry import JournalEntry
from seeker_accounting.modules.accounting.journals.models.journal_entry_line import JournalEntryLine
from seeker_accounting.modules.accounting.journals.repositories.journal_entry_repository import (
    JournalEntryRepository,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError
from seeker_accounting.platform.numbering.numbering_service import NumberingService

if TYPE_CHECKING:
    pass

_ZERO = Decimal("0")
_TWO = Decimal("0.01")

DeferralRepositoryFactory = Callable[[Session], DeferralRepository]
FiscalPeriodRepositoryFactory = Callable[[Session], FiscalPeriodRepository]
JournalEntryRepositoryFactory = Callable[[Session], JournalEntryRepository]

SOURCE_MODULE_CODE = "DEFERRALS"
DOCUMENT_TYPE_CODE = "DEFERRAL_RECOGNITION"
JOURNAL_TYPE_CODE = "DEFERRAL"


class DeferralService:
    """Manages the full lifecycle of deferral schedules."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        deferral_repository_factory: DeferralRepositoryFactory,
        fiscal_period_repository_factory: FiscalPeriodRepositoryFactory,
        journal_entry_repository_factory: JournalEntryRepositoryFactory,
        numbering_service: NumberingService,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._deferral_repository_factory = deferral_repository_factory
        self._fiscal_period_repository_factory = fiscal_period_repository_factory
        self._journal_entry_repository_factory = journal_entry_repository_factory
        self._numbering_service = numbering_service

    # ── Public API ────────────────────────────────────────────────────

    def create_schedule(self, cmd: CreateDeferralScheduleCommand) -> int:
        """Create a DRAFT deferral schedule and generate its recognition lines.

        Returns the new schedule id.
        """
        self._validate_create_command(cmd)
        with self._unit_of_work_factory() as uow:
            repo = self._deferral_repository_factory(uow.session)

            end_date = self._compute_end_date(cmd.start_date, cmd.period_count)
            schedule = DeferralSchedule(
                company_id=cmd.company_id,
                deferral_type=cmd.deferral_type,
                description=cmd.description,
                reference_text=cmd.reference_text,
                recognition_account_id=cmd.recognition_account_id,
                holding_account_id=cmd.holding_account_id,
                total_amount=cmd.total_amount,
                start_date=cmd.start_date,
                end_date=end_date,
                period_count=cmd.period_count,
                status_code=DEFERRAL_STATUS_DRAFT,
                source_document_type=cmd.source_document_type,
                source_document_id=cmd.source_document_id,
                notes=cmd.notes,
                created_by_user_id=cmd.created_by_user_id,
            )
            repo.add_schedule(schedule)
            uow.session.flush()

            lines = self._generate_lines(schedule.id, cmd.start_date, cmd.period_count, cmd.total_amount)
            for ln in lines:
                uow.session.add(ln)

            uow.commit()
            return schedule.id

    def activate_schedule(self, cmd: ActivateDeferralScheduleCommand) -> None:
        """Advance a DRAFT schedule to ACTIVE so its lines can be posted."""
        with self._unit_of_work_factory() as uow:
            repo = self._deferral_repository_factory(uow.session)
            schedule = self._require_schedule(repo, cmd.company_id, cmd.schedule_id)
            if schedule.status_code != DEFERRAL_STATUS_DRAFT:
                raise ConflictError(
                    f"Cannot activate a schedule in status '{schedule.status_code}'. "
                    "Only DRAFT schedules can be activated."
                )
            schedule.status_code = DEFERRAL_STATUS_ACTIVE
            uow.commit()

    def post_recognition_line(self, cmd: PostRecognitionLineCommand) -> int:
        """Post a single recognition instalment.

        Returns the created JournalEntry id.
        """
        with self._unit_of_work_factory() as uow:
            repo = self._deferral_repository_factory(uow.session)
            schedule = self._require_schedule(repo, cmd.company_id, cmd.schedule_id)
            if schedule.status_code != DEFERRAL_STATUS_ACTIVE:
                raise ConflictError(
                    f"Cannot post a recognition from a schedule in status '{schedule.status_code}'. "
                    "Activate the schedule first."
                )

            line = repo.get_line_by_id(cmd.schedule_id, cmd.line_id)
            if line is None:
                raise NotFoundError(f"Deferral line {cmd.line_id} not found on schedule {cmd.schedule_id}.")
            if line.status_code == LINE_STATUS_POSTED:
                raise ConflictError(f"Deferral line {cmd.line_id} is already posted.")

            fp_repo = self._fiscal_period_repository_factory(uow.session)
            period = fp_repo.get_by_id(cmd.company_id, cmd.fiscal_period_id)
            if period is None:
                raise NotFoundError(f"Fiscal period {cmd.fiscal_period_id} not found.")
            if period.status_code == "LOCKED":
                raise ValidationError("Cannot post into a locked fiscal period.")
            if period.status_code != "OPEN":
                raise ValidationError("Can only post into an open fiscal period.")

            je_id = self._build_and_post_je(
                uow.session, schedule, line, cmd.fiscal_period_id, cmd.posted_by_user_id
            )
            line.status_code = LINE_STATUS_POSTED
            line.journal_entry_id = je_id

            self._advance_schedule_if_complete(repo, schedule)
            uow.commit()
            return je_id

    def post_all_due(self, cmd: PostAllDueCommand) -> list[int]:
        """Post all PENDING lines due on or before as_of_date.

        Returns a list of created JournalEntry ids.
        """
        with self._unit_of_work_factory() as uow:
            repo = self._deferral_repository_factory(uow.session)

            fp_repo = self._fiscal_period_repository_factory(uow.session)
            period = fp_repo.get_by_id(cmd.company_id, cmd.fiscal_period_id)
            if period is None:
                raise NotFoundError(f"Fiscal period {cmd.fiscal_period_id} not found.")
            if period.status_code == "LOCKED":
                raise ValidationError("Cannot post into a locked fiscal period.")
            if period.status_code != "OPEN":
                raise ValidationError("Can only post into an open fiscal period.")

            pending = repo.list_pending_lines_due(cmd.company_id, cmd.as_of_date)
            je_ids: list[int] = []
            posted_schedule_ids: set[int] = set()
            for line in pending:
                schedule = line.schedule
                je_id = self._build_and_post_je(
                    uow.session, schedule, line, cmd.fiscal_period_id, cmd.posted_by_user_id
                )
                line.status_code = LINE_STATUS_POSTED
                line.journal_entry_id = je_id
                je_ids.append(je_id)
                posted_schedule_ids.add(schedule.id)

            for sched_id in posted_schedule_ids:
                schedule = repo.get_schedule_by_id(cmd.company_id, sched_id)
                if schedule is not None:
                    self._advance_schedule_if_complete(repo, schedule)

            uow.commit()
            return je_ids

    def cancel_schedule(self, cmd: CancelDeferralScheduleCommand) -> None:
        """Cancel a DRAFT or ACTIVE schedule.

        Posted lines are not reversed — only PENDING lines are abandoned.
        The schedule moves to CANCELLED.
        """
        with self._unit_of_work_factory() as uow:
            repo = self._deferral_repository_factory(uow.session)
            schedule = self._require_schedule(repo, cmd.company_id, cmd.schedule_id)
            if schedule.status_code == DEFERRAL_STATUS_COMPLETE:
                raise ConflictError("A COMPLETE schedule cannot be cancelled.")
            if schedule.status_code == DEFERRAL_STATUS_CANCELLED:
                raise ConflictError("Schedule is already cancelled.")
            schedule.status_code = DEFERRAL_STATUS_CANCELLED
            uow.commit()

    def get_schedule(self, company_id: int, schedule_id: int) -> DeferralScheduleDTO:
        with self._unit_of_work_factory() as uow:
            repo = self._deferral_repository_factory(uow.session)
            schedule = self._require_schedule(repo, company_id, schedule_id)
            lines = repo.get_lines_for_schedule(schedule_id)
            return self._to_dto(schedule, list(lines))

    def list_schedules(
        self,
        company_id: int,
        *,
        deferral_type: str | None = None,
        status_code: str | None = None,
    ) -> list[DeferralScheduleDTO]:
        with self._unit_of_work_factory() as uow:
            repo = self._deferral_repository_factory(uow.session)
            schedules = repo.list_schedules(company_id, deferral_type=deferral_type, status_code=status_code)
            result = []
            for s in schedules:
                lines = repo.get_lines_for_schedule(s.id)
                result.append(self._to_dto(s, list(lines)))
            return result

    # ── Internal helpers ──────────────────────────────────────────────

    def _validate_create_command(self, cmd: CreateDeferralScheduleCommand) -> None:
        if cmd.deferral_type not in (DEFERRAL_TYPE_EXPENSE, DEFERRAL_TYPE_REVENUE):
            raise ValidationError(
                f"Invalid deferral_type '{cmd.deferral_type}'. Must be EXPENSE or REVENUE."
            )
        if not cmd.description.strip():
            raise ValidationError("Description is required.")
        if cmd.total_amount <= _ZERO:
            raise ValidationError("Total amount must be positive.")
        if cmd.period_count <= 0:
            raise ValidationError("Period count must be at least 1.")
        if cmd.recognition_account_id == cmd.holding_account_id:
            raise ValidationError(
                "Recognition account and holding account must be different accounts."
            )

    @staticmethod
    def _last_day_of_month(year: int, month: int) -> date:
        last = calendar.monthrange(year, month)[1]
        return date(year, month, last)

    @classmethod
    def _compute_end_date(cls, start_date: date, period_count: int) -> date:
        month = start_date.month + period_count - 1
        year = start_date.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        return cls._last_day_of_month(year, month)

    @classmethod
    def _generate_lines(
        cls,
        schedule_id: int,
        start_date: date,
        period_count: int,
        total_amount: Decimal,
    ) -> list[DeferralScheduleLine]:
        """Generate evenly-distributed recognition lines with a rounding adjustment
        on the last line so that the sum equals total_amount exactly."""
        if period_count == 1:
            per_period = total_amount
        else:
            per_period = (total_amount / period_count).quantize(_TWO, rounding=ROUND_HALF_UP)

        lines: list[DeferralScheduleLine] = []
        cumulative = _ZERO
        for i in range(period_count):
            month = start_date.month + i
            year = start_date.year + (month - 1) // 12
            month = ((month - 1) % 12) + 1
            recognition_date = cls._last_day_of_month(year, month)

            if i == period_count - 1:
                # Last line absorbs rounding difference
                amount = total_amount - cumulative
            else:
                amount = per_period

            cumulative += amount
            lines.append(
                DeferralScheduleLine(
                    deferral_schedule_id=schedule_id,
                    line_number=i + 1,
                    recognition_date=recognition_date,
                    amount=amount,
                    status_code=LINE_STATUS_PENDING,
                )
            )
        return lines

    def _build_and_post_je(
        self,
        session: "Session",
        schedule: DeferralSchedule,
        line: DeferralScheduleLine,
        fiscal_period_id: int,
        posted_by_user_id: int | None,
    ) -> int:
        """Build a balanced 2-line posted JournalEntry for the recognition."""
        je_number = self._numbering_service.issue_next_number(
            session,
            company_id=schedule.company_id,
            document_type_code="JOURNAL_ENTRY",
        )
        description = (
            f"Deferral recognition — {schedule.description} "
            f"(period {line.line_number}/{schedule.period_count})"
        )
        je = JournalEntry(
            company_id=schedule.company_id,
            fiscal_period_id=fiscal_period_id,
            entry_number=je_number,
            entry_date=line.recognition_date,
            journal_type_code=JOURNAL_TYPE_CODE,
            description=description,
            source_module_code=SOURCE_MODULE_CODE,
            source_document_type="DEFERRAL_SCHEDULE",
            source_document_id=schedule.id,
            status_code="POSTED",
            posted_at=datetime.utcnow(),
            posted_by_user_id=posted_by_user_id,
        )
        session.add(je)
        session.flush()

        # Determine debit/credit direction based on deferral type
        if schedule.deferral_type == DEFERRAL_TYPE_EXPENSE:
            # Dr Recognition (expense) / Cr Holding (476 prepaid)
            dr_account = schedule.recognition_account_id
            cr_account = schedule.holding_account_id
        else:
            # REVENUE: Dr Holding (477 unearned) / Cr Recognition (revenue)
            dr_account = schedule.holding_account_id
            cr_account = schedule.recognition_account_id

        session.add(
            JournalEntryLine(
                journal_entry_id=je.id,
                line_number=1,
                account_id=dr_account,
                debit_amount=line.amount,
                credit_amount=_ZERO,
                line_description=f"Deferral recognition — {schedule.description}",
            )
        )
        session.add(
            JournalEntryLine(
                journal_entry_id=je.id,
                line_number=2,
                account_id=cr_account,
                debit_amount=_ZERO,
                credit_amount=line.amount,
                line_description=f"Deferral recognition — {schedule.description}",
            )
        )
        session.flush()
        return je.id

    @staticmethod
    def _advance_schedule_if_complete(repo: DeferralRepository, schedule: DeferralSchedule) -> None:
        """If all lines are POSTED, flip the schedule to COMPLETE."""
        lines = repo.get_lines_for_schedule(schedule.id)
        if all(ln.status_code == LINE_STATUS_POSTED for ln in lines):
            schedule.status_code = DEFERRAL_STATUS_COMPLETE

    @staticmethod
    def _require_schedule(
        repo: DeferralRepository, company_id: int, schedule_id: int
    ) -> DeferralSchedule:
        schedule = repo.get_schedule_by_id(company_id, schedule_id)
        if schedule is None:
            raise NotFoundError(f"Deferral schedule {schedule_id} not found.")
        return schedule

    @staticmethod
    def _to_dto(schedule: DeferralSchedule, lines: list[DeferralScheduleLine]) -> DeferralScheduleDTO:
        return DeferralScheduleDTO(
            id=schedule.id,
            company_id=schedule.company_id,
            deferral_type=schedule.deferral_type,
            description=schedule.description,
            reference_text=schedule.reference_text,
            recognition_account_id=schedule.recognition_account_id,
            holding_account_id=schedule.holding_account_id,
            total_amount=schedule.total_amount,
            start_date=schedule.start_date,
            end_date=schedule.end_date,
            period_count=schedule.period_count,
            status_code=schedule.status_code,
            source_document_type=schedule.source_document_type,
            source_document_id=schedule.source_document_id,
            notes=schedule.notes,
            lines=[
                DeferralLineDTO(
                    id=ln.id,
                    line_number=ln.line_number,
                    recognition_date=ln.recognition_date,
                    amount=ln.amount,
                    status_code=ln.status_code,
                    journal_entry_id=ln.journal_entry_id,
                )
                for ln in lines
            ],
        )
