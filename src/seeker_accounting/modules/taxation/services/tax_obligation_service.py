"""Service for tax obligations (compliance calendar entries)."""

from __future__ import annotations

import calendar
from datetime import date
from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.app.context.app_context import AppContext
from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import (
    PermissionService,
)
from seeker_accounting.modules.companies.repositories.company_repository import (
    CompanyRepository,
)
from seeker_accounting.modules.taxation.constants import (
    ALL_OBLIGATION_STATUS_CODES,
    ALL_TAX_TYPE_CODES,
    OBLIGATION_STATUS_CANCELLED,
    OBLIGATION_STATUS_OPEN,
    TAX_TYPE_CIT_INSTALLMENT,
    TAX_TYPE_CUSTOMS,
    TAX_TYPE_PATENTE,
    TAX_TYPE_TSR,
    TAX_TYPE_VAT,
    TAX_TYPE_WITHHOLDING,
)
from seeker_accounting.modules.taxation.dto.tax_compliance_dto import (
    CreateCustomsDutyObligationCommand,
    CreateTaxObligationCommand,
    GenerateAnnualPatenteObligationCommand,
    GenerateMonthlyTSRObligationsCommand,
    GenerateMonthlyVATObligationsCommand,
    GenerateMonthlyWithholdingObligationsCommand,
    GenerateQuarterlyCITInstallmentsCommand,
    TaxObligationDTO,
)
from seeker_accounting.modules.taxation.models.tax_obligation import TaxObligation
from seeker_accounting.modules.taxation.repositories.tax_obligation_repository import (
    TaxObligationRepository,
)
from seeker_accounting.platform.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService


TaxObligationRepositoryFactory = Callable[[Session], TaxObligationRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]


class TaxObligationService:
    PERMISSION_VIEW = "taxation.obligations.view"
    PERMISSION_MANAGE = "taxation.obligations.manage"

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        app_context: AppContext,
        tax_obligation_repository_factory: TaxObligationRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        permission_service: PermissionService,
        audit_service: "AuditService | None" = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._app_context = app_context
        self._tax_obligation_repository_factory = tax_obligation_repository_factory
        self._company_repository_factory = company_repository_factory
        self._permission_service = permission_service
        self._audit_service = audit_service

    # ---------------- Read ----------------

    def list_obligations(
        self,
        company_id: int,
        *,
        tax_type_code: str | None = None,
        status_code: str | None = None,
    ) -> list[TaxObligationDTO]:
        self._permission_service.require_permission(self.PERMISSION_VIEW)
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._tax_obligation_repository_factory(uow.session)
            obligations = repo.list_by_company(
                company_id,
                tax_type_code=tax_type_code,
                status_code=status_code,
            )
            return [self._to_dto(o) for o in obligations]

    def get_obligation(
        self, company_id: int, obligation_id: int
    ) -> TaxObligationDTO:
        self._permission_service.require_permission(self.PERMISSION_VIEW)
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._tax_obligation_repository_factory(uow.session)
            obligation = repo.get_by_id(company_id, obligation_id)
            if obligation is None:
                raise NotFoundError(
                    f"Tax obligation {obligation_id} was not found for this company.",
                )
            return self._to_dto(obligation)

    # ---------------- Write ----------------

    def create_obligation(
        self,
        company_id: int,
        command: CreateTaxObligationCommand,
        actor_user_id: int | None = None,
    ) -> TaxObligationDTO:
        self._permission_service.require_permission(self.PERMISSION_MANAGE)

        tax_type_code = self._validate_tax_type(command.tax_type_code)
        self._validate_period(command.period_start, command.period_end)
        if command.due_date < command.period_end:
            raise ValidationError(
                "Due date must fall on or after the end of the obligation period.",
            )

        notes = (command.notes or "").strip() or None
        if notes is not None and len(notes) > 500:
            raise ValidationError("Notes are too long (max 500 characters).")

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._tax_obligation_repository_factory(uow.session)

            existing = repo.get_by_period(
                company_id,
                tax_type_code,
                command.period_start,
                command.period_end,
            )
            if existing is not None:
                raise ConflictError(
                    "An obligation already exists for this tax type and period.",
                )

            obligation = TaxObligation(
                company_id=company_id,
                tax_type_code=tax_type_code,
                period_start=command.period_start,
                period_end=command.period_end,
                due_date=command.due_date,
                status_code=OBLIGATION_STATUS_OPEN,
                notes=notes,
            )
            repo.add(obligation)

            try:
                uow.commit()
            except IntegrityError as exc:  # pragma: no cover - defensive
                raise ConflictError(
                    "Tax obligation could not be saved due to a data conflict.",
                ) from exc

            self._record_audit(
                company_id,
                "TAX_OBLIGATION_GENERATED",
                obligation.id,
                f"Created {tax_type_code} obligation for "
                f"{command.period_start.isoformat()} – {command.period_end.isoformat()}.",
                actor_user_id,
            )

            return self._to_dto(obligation)

    def cancel_obligation(
        self,
        company_id: int,
        obligation_id: int,
        actor_user_id: int | None = None,
    ) -> TaxObligationDTO:
        self._permission_service.require_permission(self.PERMISSION_MANAGE)
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._tax_obligation_repository_factory(uow.session)
            obligation = repo.get_by_id(company_id, obligation_id)
            if obligation is None:
                raise NotFoundError(
                    f"Tax obligation {obligation_id} was not found for this company.",
                )
            if obligation.tax_returns:
                raise ValidationError(
                    "Cannot cancel an obligation that already has tax returns. "
                    "Cancel or delete the returns first.",
                )
            obligation.status_code = OBLIGATION_STATUS_CANCELLED
            uow.commit()

            self._record_audit(
                company_id,
                "TAX_OBLIGATION_CANCELLED",
                obligation.id,
                f"Cancelled {obligation.tax_type_code} obligation "
                f"{obligation.period_start.isoformat()} – {obligation.period_end.isoformat()}.",
                actor_user_id,
            )

            return self._to_dto(obligation)

    def generate_monthly_vat_obligations(
        self,
        company_id: int,
        command: GenerateMonthlyVATObligationsCommand,
        actor_user_id: int | None = None,
    ) -> list[TaxObligationDTO]:
        """Generate the 12 monthly VAT obligations for a year (idempotent)."""
        self._permission_service.require_permission(self.PERMISSION_MANAGE)

        if command.year < 2000 or command.year > 2100:
            raise ValidationError("Year is outside the supported range.")
        if not 1 <= command.due_day_of_next_month <= 28:
            raise ValidationError(
                "Due day of next month must be between 1 and 28.",
            )

        results: list[TaxObligation] = []

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._tax_obligation_repository_factory(uow.session)

            for month in range(1, 13):
                period_start = date(command.year, month, 1)
                last_day = calendar.monthrange(command.year, month)[1]
                period_end = date(command.year, month, last_day)
                # Due in the following month
                if month == 12:
                    due_year, due_month = command.year + 1, 1
                else:
                    due_year, due_month = command.year, month + 1
                due_day = min(
                    command.due_day_of_next_month,
                    calendar.monthrange(due_year, due_month)[1],
                )
                due_date = date(due_year, due_month, due_day)

                existing = repo.get_by_period(
                    company_id, TAX_TYPE_VAT, period_start, period_end
                )
                if existing is not None:
                    results.append(existing)
                    continue

                obligation = TaxObligation(
                    company_id=company_id,
                    tax_type_code=TAX_TYPE_VAT,
                    period_start=period_start,
                    period_end=period_end,
                    due_date=due_date,
                    status_code=OBLIGATION_STATUS_OPEN,
                )
                repo.add(obligation)
                results.append(obligation)

            try:
                uow.commit()
            except IntegrityError as exc:  # pragma: no cover - defensive
                raise ConflictError(
                    "Monthly VAT obligations could not be saved due to a data conflict.",
                ) from exc

            self._record_audit(
                company_id,
                "TAX_OBLIGATION_GENERATED",
                None,
                f"Generated monthly VAT obligations for {command.year}.",
                actor_user_id,
            )

            return [self._to_dto(o) for o in results]

    def generate_quarterly_cit_installments(
        self,
        company_id: int,
        command: GenerateQuarterlyCITInstallmentsCommand,
        actor_user_id: int | None = None,
    ) -> list[TaxObligationDTO]:
        """Generate the four quarterly CIT installment obligations (idempotent).

        Quarter periods are calendar quarters (Q1: Jan-Mar … Q4: Oct-Dec).
        Each quarter is due in the first month after its period end on the
        configured day (default 15). Existing obligations for the same
        period are reused so reruns are safe.
        """
        self._permission_service.require_permission(self.PERMISSION_MANAGE)

        if command.year < 2000 or command.year > 2100:
            raise ValidationError("Year is outside the supported range.")
        if not 1 <= command.due_day_of_next_month <= 28:
            raise ValidationError(
                "Due day of next month must be between 1 and 28.",
            )

        # Quarter end-month → (period_start_month, period_end_month).
        quarters = (
            (1, 3),
            (4, 6),
            (7, 9),
            (10, 12),
        )

        results: list[TaxObligation] = []

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._tax_obligation_repository_factory(uow.session)

            for start_month, end_month in quarters:
                period_start = date(command.year, start_month, 1)
                last_day = calendar.monthrange(command.year, end_month)[1]
                period_end = date(command.year, end_month, last_day)
                # Due in the first month after the quarter end.
                if end_month == 12:
                    due_year, due_month = command.year + 1, 1
                else:
                    due_year, due_month = command.year, end_month + 1
                due_day = min(
                    command.due_day_of_next_month,
                    calendar.monthrange(due_year, due_month)[1],
                )
                due_date = date(due_year, due_month, due_day)

                existing = repo.get_by_period(
                    company_id, TAX_TYPE_CIT_INSTALLMENT, period_start, period_end
                )
                if existing is not None:
                    results.append(existing)
                    continue

                obligation = TaxObligation(
                    company_id=company_id,
                    tax_type_code=TAX_TYPE_CIT_INSTALLMENT,
                    period_start=period_start,
                    period_end=period_end,
                    due_date=due_date,
                    status_code=OBLIGATION_STATUS_OPEN,
                )
                repo.add(obligation)
                results.append(obligation)

            try:
                uow.commit()
            except IntegrityError as exc:  # pragma: no cover - defensive
                raise ConflictError(
                    "Quarterly CIT installments could not be saved due to a data conflict.",
                ) from exc

            self._record_audit(
                company_id,
                "TAX_OBLIGATION_GENERATED",
                None,
                f"Generated quarterly CIT installments for {command.year}.",
                actor_user_id,
            )

            return [self._to_dto(o) for o in results]

    # ---------- Slice T18 / T19 / T20 / T21 ----------

    def _generate_monthly_obligations(
        self,
        company_id: int,
        tax_type_code: str,
        year: int,
        due_day_of_next_month: int,
        audit_label: str,
        actor_user_id: int | None,
    ) -> list[TaxObligation]:
        """Shared monthly-cadence generator (idempotent via period uniqueness)."""

        if year < 2000 or year > 2100:
            raise ValidationError("Year is outside the supported range.")
        if not 1 <= due_day_of_next_month <= 28:
            raise ValidationError(
                "Due day of next month must be between 1 and 28.",
            )

        results: list[TaxObligation] = []
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._tax_obligation_repository_factory(uow.session)

            for month in range(1, 13):
                period_start = date(year, month, 1)
                last_day = calendar.monthrange(year, month)[1]
                period_end = date(year, month, last_day)
                if month == 12:
                    due_year, due_month = year + 1, 1
                else:
                    due_year, due_month = year, month + 1
                due_day = min(
                    due_day_of_next_month,
                    calendar.monthrange(due_year, due_month)[1],
                )
                due_date = date(due_year, due_month, due_day)

                existing = repo.get_by_period(
                    company_id, tax_type_code, period_start, period_end
                )
                if existing is not None:
                    results.append(existing)
                    continue

                obligation = TaxObligation(
                    company_id=company_id,
                    tax_type_code=tax_type_code,
                    period_start=period_start,
                    period_end=period_end,
                    due_date=due_date,
                    status_code=OBLIGATION_STATUS_OPEN,
                )
                repo.add(obligation)
                results.append(obligation)

            try:
                uow.commit()
            except IntegrityError as exc:  # pragma: no cover - defensive
                raise ConflictError(
                    f"Monthly {tax_type_code} obligations could not be saved "
                    "due to a data conflict.",
                ) from exc

            self._record_audit(
                company_id,
                "TAX_OBLIGATION_GENERATED",
                None,
                audit_label,
                actor_user_id,
            )
        return results

    def generate_monthly_withholding_obligations(
        self,
        company_id: int,
        command: GenerateMonthlyWithholdingObligationsCommand,
        actor_user_id: int | None = None,
    ) -> list[TaxObligationDTO]:
        """Generate the 12 monthly withholding-tax obligations (Slice T18)."""
        self._permission_service.require_permission(self.PERMISSION_MANAGE)
        results = self._generate_monthly_obligations(
            company_id,
            TAX_TYPE_WITHHOLDING,
            command.year,
            command.due_day_of_next_month,
            f"Generated monthly withholding-tax obligations for {command.year}.",
            actor_user_id,
        )
        return [self._to_dto(o) for o in results]

    def generate_monthly_tsr_obligations(
        self,
        company_id: int,
        command: GenerateMonthlyTSRObligationsCommand,
        actor_user_id: int | None = None,
    ) -> list[TaxObligationDTO]:
        """Generate the 12 monthly TSR (specific-service tax) obligations (Slice T20)."""
        self._permission_service.require_permission(self.PERMISSION_MANAGE)
        results = self._generate_monthly_obligations(
            company_id,
            TAX_TYPE_TSR,
            command.year,
            command.due_day_of_next_month,
            f"Generated monthly TSR obligations for {command.year}.",
            actor_user_id,
        )
        return [self._to_dto(o) for o in results]

    def generate_annual_patente_obligation(
        self,
        company_id: int,
        command: GenerateAnnualPatenteObligationCommand,
        actor_user_id: int | None = None,
    ) -> TaxObligationDTO:
        """Generate the single annual Patente obligation (Slice T19)."""
        self._permission_service.require_permission(self.PERMISSION_MANAGE)

        if command.year < 2000 or command.year > 2100:
            raise ValidationError("Year is outside the supported range.")
        if not 1 <= command.due_month <= 12:
            raise ValidationError("Due month must be between 1 and 12.")
        last_day = calendar.monthrange(command.year, command.due_month)[1]
        if not 1 <= command.due_day <= last_day:
            raise ValidationError(
                f"Due day must be between 1 and {last_day} for the chosen month.",
            )

        period_start = date(command.year, 1, 1)
        period_end = date(command.year, 12, 31)
        due_date = date(command.year, command.due_month, command.due_day)

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._tax_obligation_repository_factory(uow.session)

            existing = repo.get_by_period(
                company_id, TAX_TYPE_PATENTE, period_start, period_end
            )
            if existing is not None:
                return self._to_dto(existing)

            obligation = TaxObligation(
                company_id=company_id,
                tax_type_code=TAX_TYPE_PATENTE,
                period_start=period_start,
                period_end=period_end,
                due_date=due_date,
                status_code=OBLIGATION_STATUS_OPEN,
            )
            repo.add(obligation)

            try:
                uow.commit()
            except IntegrityError as exc:  # pragma: no cover - defensive
                raise ConflictError(
                    "Annual Patente obligation could not be saved due to a data conflict.",
                ) from exc

            self._record_audit(
                company_id,
                "TAX_OBLIGATION_GENERATED",
                obligation.id,
                f"Generated annual Patente obligation for {command.year}.",
                actor_user_id,
            )
            return self._to_dto(obligation)

    def create_customs_duty_obligation(
        self,
        company_id: int,
        command: CreateCustomsDutyObligationCommand,
        actor_user_id: int | None = None,
    ) -> TaxObligationDTO:
        """Record a per-declaration customs-duty obligation (Slice T21).

        Customs is event-driven (one obligation per import declaration),
        not periodic. ``period_start`` and ``period_end`` are both set
        to the declaration date so the unique ``(company_id, tax_type,
        period_start, period_end)`` index lets us record multiple
        declarations on the same day only when they have a distinct
        reference embedded in ``notes`` -- callers are responsible for
        keeping declaration references unique. The DTO does not expose a
        dedicated declaration-reference column; this is a deliberate
        Phase-1 simplification (a dedicated customs register lives in a
        later slice).
        """
        self._permission_service.require_permission(self.PERMISSION_MANAGE)

        if command.declaration_date is None:
            raise ValidationError("Declaration date is required.")
        if command.due_date is None:
            raise ValidationError("Due date is required.")
        if command.due_date < command.declaration_date:
            raise ValidationError(
                "Due date must fall on or after the declaration date.",
            )

        notes = command.notes
        if command.declaration_reference:
            ref = f"Declaration ref: {command.declaration_reference}"
            notes = f"{ref}\n{notes}" if notes else ref

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._tax_obligation_repository_factory(uow.session)

            existing = repo.get_by_period(
                company_id,
                TAX_TYPE_CUSTOMS,
                command.declaration_date,
                command.declaration_date,
            )
            if existing is not None:
                # Surface conflict -- caller must vary the declaration
                # date or cancel the existing entry first.
                raise ConflictError(
                    "A customs-duty obligation already exists for this "
                    "declaration date. Cancel the existing entry or vary "
                    "the date before recording another.",
                )

            obligation = TaxObligation(
                company_id=company_id,
                tax_type_code=TAX_TYPE_CUSTOMS,
                period_start=command.declaration_date,
                period_end=command.declaration_date,
                due_date=command.due_date,
                status_code=OBLIGATION_STATUS_OPEN,
                notes=notes,
            )
            repo.add(obligation)

            try:
                uow.commit()
            except IntegrityError as exc:  # pragma: no cover - defensive
                raise ConflictError(
                    "Customs-duty obligation could not be saved due to a data conflict.",
                ) from exc

            self._record_audit(
                company_id,
                "TAX_OBLIGATION_GENERATED",
                obligation.id,
                (
                    f"Recorded customs-duty obligation for declaration "
                    f"{command.declaration_reference or '(no ref)'} on "
                    f"{command.declaration_date.isoformat()}."
                ),
                actor_user_id,
            )
            return self._to_dto(obligation)

    # ---------------- Helpers ----------------

    @staticmethod
    def _validate_tax_type(value: str | None) -> str:
        if value is None:
            raise ValidationError("Tax type is required.")
        normalized = value.strip().upper()
        if normalized not in ALL_TAX_TYPE_CODES:
            raise ValidationError(f"Tax type '{value}' is not recognized.")
        return normalized

    @staticmethod
    def _validate_period(period_start: date, period_end: date) -> None:
        if period_start is None or period_end is None:
            raise ValidationError("Period start and end are required.")
        if period_end < period_start:
            raise ValidationError(
                "Period end must fall on or after the period start.",
            )

    @staticmethod
    def _validate_status(value: str) -> str:
        if value not in ALL_OBLIGATION_STATUS_CODES:
            raise ValidationError(f"Obligation status '{value}' is not recognized.")
        return value

    def _require_company_exists(self, session: Session, company_id: int) -> None:
        company_repo = self._company_repository_factory(session)
        if company_repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

    @staticmethod
    def _to_dto(o: TaxObligation) -> TaxObligationDTO:
        return TaxObligationDTO(
            id=o.id,
            company_id=o.company_id,
            tax_type_code=o.tax_type_code,
            period_start=o.period_start,
            period_end=o.period_end,
            due_date=o.due_date,
            status_code=o.status_code,
            notes=o.notes,
            created_at=o.created_at,
            updated_at=o.updated_at,
        )

    def _record_audit(
        self,
        company_id: int,
        event_type_code: str,
        entity_id: int | None,
        description: str,
        actor_user_id: int | None,
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
                    entity_type="TaxObligation",
                    entity_id=entity_id,
                    description=description,
                ),
            )
        except Exception:
            pass
