from __future__ import annotations

from calendar import month_name
from datetime import date, timedelta
from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.audit.dto.audit_event_dto import RecordAuditEventCommand
from seeker_accounting.modules.audit.event_type_catalog import (
    FISCAL_PERIODS_GENERATED,
    FISCAL_YEAR_CREATED,
    MODULE_FISCAL,
)
from seeker_accounting.modules.accounting.fiscal_periods.dto.fiscal_calendar_commands import (
    CreateFiscalYearCommand,
    GenerateFiscalPeriodsCommand,
)
from seeker_accounting.modules.accounting.fiscal_periods.dto.fiscal_calendar_dto import (
    FiscalCalendarDTO,
    FiscalPeriodDTO,
    FiscalPeriodListItemDTO,
    FiscalYearDTO,
    FiscalYearListItemDTO,
)
from seeker_accounting.modules.accounting.fiscal_periods.models.fiscal_period import FiscalPeriod
from seeker_accounting.modules.accounting.fiscal_periods.models.fiscal_year import FiscalYear

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService
from seeker_accounting.modules.accounting.fiscal_periods.repositories.fiscal_period_repository import (
    FiscalPeriodRepository,
)
from seeker_accounting.modules.accounting.fiscal_periods.repositories.fiscal_year_repository import (
    FiscalYearRepository,
)
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

FiscalYearRepositoryFactory = Callable[[Session], FiscalYearRepository]
FiscalPeriodRepositoryFactory = Callable[[Session], FiscalPeriodRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]


class FiscalCalendarService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        fiscal_year_repository_factory: FiscalYearRepositoryFactory,
        fiscal_period_repository_factory: FiscalPeriodRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        permission_service: PermissionService,
        audit_service: "AuditService | None" = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._fiscal_year_repository_factory = fiscal_year_repository_factory
        self._fiscal_period_repository_factory = fiscal_period_repository_factory
        self._company_repository_factory = company_repository_factory
        self._permission_service = permission_service
        self._audit_service = audit_service

    def list_fiscal_years(self, company_id: int) -> list[FiscalYearListItemDTO]:
        self._permission_service.require_permission("fiscal.years.view")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_fiscal_year_repository(uow.session)
            return [self._to_fiscal_year_list_item_dto(row) for row in repository.list_by_company(company_id)]

    def get_fiscal_year(self, company_id: int, fiscal_year_id: int) -> FiscalYearDTO:
        self._permission_service.require_permission("fiscal.years.view")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            fiscal_year_repository = self._require_fiscal_year_repository(uow.session)
            fiscal_period_repository = self._require_fiscal_period_repository(uow.session)

            fiscal_year = fiscal_year_repository.get_by_id(company_id, fiscal_year_id)
            if fiscal_year is None:
                raise NotFoundError(f"Fiscal year with id {fiscal_year_id} was not found.")

            periods = fiscal_period_repository.list_for_year(company_id, fiscal_year_id)
            return self._to_fiscal_year_dto(fiscal_year, periods)

    def create_fiscal_year(self, company_id: int, command: CreateFiscalYearCommand) -> FiscalYearDTO:
        self._permission_service.require_permission("fiscal.years.create")
        year_code = self._require_code(command.year_code, "Fiscal year code")
        year_name = self._require_text(command.year_name, "Fiscal year name")
        start_date = command.start_date
        end_date = command.end_date
        if start_date >= end_date:
            raise ValidationError("Fiscal year start date must be before end date.")

        status_code = self._normalize_status(command.status_code, {"DRAFT", "OPEN", "CLOSED"})

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_fiscal_year_repository(uow.session)

            if repository.get_by_code(company_id, year_code) is not None:
                raise ConflictError("A fiscal year with this code already exists for the company.")

            existing_years = repository.list_by_company(company_id, active_only=False)
            for existing_year in existing_years:
                if self._dates_overlap(start_date, end_date, existing_year.start_date, existing_year.end_date):
                    raise ConflictError("Fiscal years cannot overlap within the same company.")

            fiscal_year = FiscalYear(
                company_id=company_id,
                year_code=year_code,
                year_name=year_name,
                start_date=start_date,
                end_date=end_date,
                status_code=status_code,
                is_active=bool(command.is_active),
            )
            repository.add(fiscal_year)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_fiscal_year_integrity_error(exc) from exc

            self._record_audit(
                company_id, FISCAL_YEAR_CREATED, "FiscalYear",
                fiscal_year.id, f"Fiscal year '{year_code}' created.",
            )
            return self._to_fiscal_year_dto(fiscal_year, ())

    def generate_periods(
        self,
        company_id: int,
        fiscal_year_id: int,
        command: GenerateFiscalPeriodsCommand,
    ) -> FiscalCalendarDTO:
        self._permission_service.require_permission("fiscal.periods.generate")
        if command.periods_per_year != 12:
            raise ValidationError("Only monthly fiscal period generation is supported in this slice.")
        if command.include_adjustment_period:
            raise ValidationError("Adjustment period generation is deferred from the first fiscal calendar pass.")

        opening_status_code = self._normalize_status(command.opening_status_code, {"OPEN", "CLOSED"})

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            fiscal_year_repository = self._require_fiscal_year_repository(uow.session)
            fiscal_period_repository = self._require_fiscal_period_repository(uow.session)

            fiscal_year = fiscal_year_repository.get_by_id(company_id, fiscal_year_id)
            if fiscal_year is None:
                raise NotFoundError(f"Fiscal year with id {fiscal_year_id} was not found.")

            existing_periods = fiscal_period_repository.list_for_year(company_id, fiscal_year_id)
            if existing_periods:
                raise ConflictError("Fiscal periods have already been generated for this fiscal year.")

            periods = self._build_monthly_periods(
                company_id=company_id,
                fiscal_year=fiscal_year,
                opening_status_code=opening_status_code,
            )
            for period in periods:
                fiscal_period_repository.add(period)

            fiscal_year.status_code = "OPEN" if opening_status_code == "OPEN" else fiscal_year.status_code
            fiscal_year_repository.save(fiscal_year)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Fiscal periods could not be generated.") from exc

            self._record_audit(
                company_id, FISCAL_PERIODS_GENERATED, "FiscalYear",
                fiscal_year.id,
                f"Fiscal periods generated for year '{fiscal_year.year_code}' ({len(periods)} periods).",
            )
            period_dtos = tuple(
                self._to_fiscal_period_dto(period, fiscal_year.year_code)
                for period in fiscal_period_repository.list_for_year(company_id, fiscal_year_id)
            )
            return FiscalCalendarDTO(
                fiscal_year=self._to_fiscal_year_dto(fiscal_year, period_dtos),
                periods=period_dtos,
            )

    def list_periods(
        self,
        company_id: int,
        fiscal_year_id: int | None = None,
    ) -> list[FiscalPeriodListItemDTO]:
        self._permission_service.require_permission("fiscal.periods.view")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            fiscal_period_repository = self._require_fiscal_period_repository(uow.session)
            fiscal_year_repository = self._require_fiscal_year_repository(uow.session)
            year_code_by_id = {
                fiscal_year.id: fiscal_year.year_code
                for fiscal_year in fiscal_year_repository.list_by_company(company_id, active_only=False)
            }
            return [
                self._to_fiscal_period_list_item_dto(period, year_code_by_id.get(period.fiscal_year_id, ""))
                for period in fiscal_period_repository.list_by_company(company_id, fiscal_year_id=fiscal_year_id)
            ]

    def get_current_period(self, company_id: int, target_date: date | None = None) -> FiscalPeriodDTO | None:
        self._permission_service.require_permission("fiscal.periods.view")
        target = target_date or date.today()

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            fiscal_period_repository = self._require_fiscal_period_repository(uow.session)
            fiscal_year_repository = self._require_fiscal_year_repository(uow.session)

            period = fiscal_period_repository.get_covering_date(company_id, target)
            if period is None:
                return None

            fiscal_year = fiscal_year_repository.get_by_id(company_id, period.fiscal_year_id)
            year_code = fiscal_year.year_code if fiscal_year is not None else ""
            return self._to_fiscal_period_dto(period, year_code)

    def _require_fiscal_year_repository(self, session: Session | None) -> FiscalYearRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._fiscal_year_repository_factory(session)

    def _require_fiscal_period_repository(self, session: Session | None) -> FiscalPeriodRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._fiscal_period_repository_factory(session)

    def _require_company_exists(self, session: Session | None, company_id: int) -> None:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        company_repository = self._company_repository_factory(session)
        if company_repository.get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

    def _build_monthly_periods(
        self,
        *,
        company_id: int,
        fiscal_year: FiscalYear,
        opening_status_code: str,
    ) -> list[FiscalPeriod]:
        periods: list[FiscalPeriod] = []
        current_start = fiscal_year.start_date

        for period_number in range(1, 13):
            if period_number == 12:
                current_end = fiscal_year.end_date
            else:
                next_start = self._add_months(current_start, 1)
                current_end = next_start - timedelta(days=1)
                if current_end > fiscal_year.end_date:
                    raise ValidationError("Fiscal year dates do not align cleanly with monthly period generation.")

            period_name = f"{month_name[current_start.month]} {current_start.year}"
            periods.append(
                FiscalPeriod(
                    company_id=company_id,
                    fiscal_year_id=fiscal_year.id,
                    period_number=period_number,
                    period_code=f"{fiscal_year.year_code}-{period_number:02d}",
                    period_name=period_name,
                    start_date=current_start,
                    end_date=current_end,
                    status_code=opening_status_code,
                    is_adjustment_period=False,
                )
            )
            current_start = current_end + timedelta(days=1)

        if periods[-1].end_date != fiscal_year.end_date:
            raise ValidationError("Generated periods do not cover the fiscal year cleanly.")
        return periods

    def _add_months(self, value: date, months: int) -> date:
        month_index = (value.month - 1) + months
        year = value.year + month_index // 12
        month = month_index % 12 + 1
        day = value.day

        while True:
            try:
                return date(year, month, day)
            except ValueError:
                day -= 1
                if day <= 0:
                    raise ValidationError("Fiscal year dates do not support monthly period generation.")

    def _dates_overlap(self, start_a: date, end_a: date, start_b: date, end_b: date) -> bool:
        return start_a <= end_b and start_b <= end_a

    def _require_text(self, value: str, label: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValidationError(f"{label} is required.")
        return normalized

    def _require_code(self, value: str, label: str) -> str:
        normalized = self._require_text(value, label).upper().replace(" ", "")
        if not normalized:
            raise ValidationError(f"{label} is required.")
        return normalized

    def _normalize_status(self, value: str, allowed_values: set[str]) -> str:
        normalized = self._require_text(value, "Status").upper()
        if normalized not in allowed_values:
            raise ValidationError(f"Status must be one of: {', '.join(sorted(allowed_values))}.")
        return normalized

    def _translate_fiscal_year_integrity_error(self, exc: IntegrityError) -> ValidationError | ConflictError:
        message = str(exc.orig).lower() if exc.orig is not None else str(exc).lower()
        if "unique" in message or "uq_fiscal_years" in message:
            return ConflictError("Fiscal year data conflicts with an existing fiscal year.")
        return ValidationError("Fiscal year data could not be saved.")

    def _to_fiscal_year_list_item_dto(self, row: FiscalYear) -> FiscalYearListItemDTO:
        return FiscalYearListItemDTO(
            id=row.id,
            company_id=row.company_id,
            year_code=row.year_code,
            year_name=row.year_name,
            start_date=row.start_date,
            end_date=row.end_date,
            status_code=row.status_code,
            is_active=row.is_active,
            updated_at=row.updated_at,
        )

    def _to_fiscal_period_list_item_dto(
        self,
        row: FiscalPeriod,
        fiscal_year_code: str,
    ) -> FiscalPeriodListItemDTO:
        _ = fiscal_year_code
        return FiscalPeriodListItemDTO(
            id=row.id,
            company_id=row.company_id,
            fiscal_year_id=row.fiscal_year_id,
            period_number=row.period_number,
            period_code=row.period_code,
            period_name=row.period_name,
            start_date=row.start_date,
            end_date=row.end_date,
            status_code=row.status_code,
            is_adjustment_period=row.is_adjustment_period,
            updated_at=row.updated_at,
        )

    def _to_fiscal_year_dto(
        self,
        row: FiscalYear,
        periods: tuple[FiscalPeriodDTO, ...] | list[FiscalPeriod] | tuple[FiscalPeriod, ...],
    ) -> FiscalYearDTO:
        period_dtos: tuple[FiscalPeriodDTO, ...]
        if periods and isinstance(periods[0], FiscalPeriodDTO):  # type: ignore[index]
            period_dtos = tuple(periods)  # type: ignore[arg-type]
        else:
            period_dtos = tuple(self._to_fiscal_period_dto(period, row.year_code) for period in periods)  # type: ignore[arg-type]
        return FiscalYearDTO(
            id=row.id,
            company_id=row.company_id,
            year_code=row.year_code,
            year_name=row.year_name,
            start_date=row.start_date,
            end_date=row.end_date,
            status_code=row.status_code,
            is_active=row.is_active,
            created_at=row.created_at,
            updated_at=row.updated_at,
            periods=period_dtos,
        )

    def _to_fiscal_period_dto(self, row: FiscalPeriod, fiscal_year_code: str) -> FiscalPeriodDTO:
        return FiscalPeriodDTO(
            id=row.id,
            company_id=row.company_id,
            fiscal_year_id=row.fiscal_year_id,
            fiscal_year_code=fiscal_year_code,
            period_number=row.period_number,
            period_code=row.period_code,
            period_name=row.period_name,
            start_date=row.start_date,
            end_date=row.end_date,
            status_code=row.status_code,
            is_adjustment_period=row.is_adjustment_period,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _record_audit(
        self,
        company_id: int,
        event_type_code: str,
        entity_type: str,
        entity_id: int | None,
        description: str,
        detail_json: str | None = None,
    ) -> None:
        if self._audit_service is None:
            return
        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type_code,
                    module_code=MODULE_FISCAL,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    description=description,
                    detail_json=detail_json,
                ),
            )
        except Exception:  # noqa: BLE001 — audit must never break fiscal calendar flow
            pass
