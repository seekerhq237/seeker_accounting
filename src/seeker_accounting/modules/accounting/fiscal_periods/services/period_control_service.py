from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.accounting.fiscal_periods.dto.fiscal_calendar_dto import (
    FiscalPeriodDTO,
    PeriodStatusChangeResultDTO,
)
from seeker_accounting.modules.accounting.fiscal_periods.models.fiscal_period import FiscalPeriod
from seeker_accounting.modules.accounting.fiscal_periods.repositories.fiscal_period_repository import (
    FiscalPeriodRepository,
)
from seeker_accounting.modules.accounting.fiscal_periods.repositories.fiscal_year_repository import (
    FiscalYearRepository,
)
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.audit.dto.audit_event_dto import RecordAuditEventCommand
from seeker_accounting.modules.audit.event_type_catalog import (
    FISCAL_PERIOD_CLOSED,
    FISCAL_PERIOD_LOCKED,
    FISCAL_PERIOD_OPENED,
    FISCAL_PERIOD_REOPENED,
    MODULE_FISCAL,
)
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

from seeker_accounting.platform.exceptions import (
    NotFoundError,
    PeriodLockedError,
    ValidationError,
)

FiscalPeriodRepositoryFactory = Callable[[Session], FiscalPeriodRepository]
FiscalYearRepositoryFactory = Callable[[Session], FiscalYearRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]


class PeriodControlService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        fiscal_period_repository_factory: FiscalPeriodRepositoryFactory,
        fiscal_year_repository_factory: FiscalYearRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        permission_service: PermissionService,
        audit_service: "AuditService | None" = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._fiscal_period_repository_factory = fiscal_period_repository_factory
        self._fiscal_year_repository_factory = fiscal_year_repository_factory
        self._company_repository_factory = company_repository_factory
        self._permission_service = permission_service
        self._audit_service = audit_service

    def open_period(
        self,
        company_id: int,
        fiscal_period_id: int,
        actor_user_id: int | None = None,
    ) -> PeriodStatusChangeResultDTO:
        self._permission_service.require_permission("fiscal.periods.open")
        return self._change_period_status(
            company_id=company_id,
            fiscal_period_id=fiscal_period_id,
            target_status_code="OPEN",
            actor_user_id=actor_user_id,
        )

    def close_period(
        self,
        company_id: int,
        fiscal_period_id: int,
        actor_user_id: int | None = None,
    ) -> PeriodStatusChangeResultDTO:
        self._permission_service.require_permission("fiscal.periods.close")
        return self._change_period_status(
            company_id=company_id,
            fiscal_period_id=fiscal_period_id,
            target_status_code="CLOSED",
            actor_user_id=actor_user_id,
        )

    def reopen_period(
        self,
        company_id: int,
        fiscal_period_id: int,
        actor_user_id: int | None = None,
    ) -> PeriodStatusChangeResultDTO:
        self._permission_service.require_permission("fiscal.periods.reopen")
        return self._change_period_status(
            company_id=company_id,
            fiscal_period_id=fiscal_period_id,
            target_status_code="OPEN",
            actor_user_id=actor_user_id,
            reopen=True,
        )

    def lock_period(
        self,
        company_id: int,
        fiscal_period_id: int,
        actor_user_id: int | None = None,
    ) -> PeriodStatusChangeResultDTO:
        self._permission_service.require_permission("fiscal.periods.lock")
        return self._change_period_status(
            company_id=company_id,
            fiscal_period_id=fiscal_period_id,
            target_status_code="LOCKED",
            actor_user_id=actor_user_id,
        )

    def validate_posting_date(self, company_id: int, posting_date: date) -> FiscalPeriodDTO:
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            fiscal_period_repository = self._require_fiscal_period_repository(uow.session)
            fiscal_year_repository = self._require_fiscal_year_repository(uow.session)

            period = fiscal_period_repository.get_covering_date(company_id, posting_date)
            if period is None:
                raise ValidationError("Posting date must fall within an existing fiscal period.")
            if period.status_code == "LOCKED":
                raise PeriodLockedError("Posting is blocked because the fiscal period is locked.")
            if period.status_code != "OPEN":
                raise ValidationError("Posting is only allowed into open fiscal periods.")

            fiscal_year = fiscal_year_repository.get_by_id(company_id, period.fiscal_year_id)
            year_code = fiscal_year.year_code if fiscal_year is not None else ""
            return self._to_fiscal_period_dto(period, year_code)

    def is_posting_allowed(self, company_id: int, posting_date: date) -> bool:
        try:
            self.validate_posting_date(company_id, posting_date)
        except (ValidationError, PeriodLockedError, NotFoundError):
            return False
        return True

    def _change_period_status(
        self,
        *,
        company_id: int,
        fiscal_period_id: int,
        target_status_code: str,
        actor_user_id: int | None,
        reopen: bool = False,
    ) -> PeriodStatusChangeResultDTO:
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_fiscal_period_repository(uow.session)

            period = repository.get_by_id(company_id, fiscal_period_id)
            if period is None:
                raise NotFoundError(f"Fiscal period with id {fiscal_period_id} was not found.")

            self._check_sensitive_action_permission(actor_user_id, target_status_code)
            previous_status_code = period.status_code
            self._validate_status_transition(
                current_status_code=previous_status_code,
                target_status_code=target_status_code,
                reopen=reopen,
            )

            period.status_code = target_status_code
            repository.save(period)
            uow.commit()

            _STATUS_EVENT = {
                "OPEN": FISCAL_PERIOD_OPENED,
                "CLOSED": FISCAL_PERIOD_CLOSED,
                "LOCKED": FISCAL_PERIOD_LOCKED,
            }
            evt = FISCAL_PERIOD_REOPENED if reopen else _STATUS_EVENT.get(target_status_code, FISCAL_PERIOD_OPENED)
            self._record_audit(
                company_id, evt, "FiscalPeriod", period.id,
                f"Period '{period.period_code}' changed from {previous_status_code} to {target_status_code}.",
            )

            return PeriodStatusChangeResultDTO(
                fiscal_period_id=period.id,
                period_code=period.period_code,
                previous_status_code=previous_status_code,
                status_code=period.status_code,
                actor_user_id=actor_user_id,
                updated_at=period.updated_at,
            )

    def _validate_status_transition(
        self,
        *,
        current_status_code: str,
        target_status_code: str,
        reopen: bool,
    ) -> None:
        if current_status_code == "LOCKED":
            raise PeriodLockedError("Locked fiscal periods cannot be changed through the ordinary workflow.")
        if current_status_code == target_status_code:
            raise ValidationError(f"The fiscal period is already {target_status_code.lower()}.")

        if target_status_code == "CLOSED" and current_status_code != "OPEN":
            raise ValidationError("Only open fiscal periods can be closed.")
        if target_status_code == "LOCKED" and current_status_code != "CLOSED":
            raise ValidationError("Only closed fiscal periods can be locked.")
        if target_status_code == "OPEN":
            if reopen and current_status_code != "CLOSED":
                raise ValidationError("Only closed fiscal periods can be reopened.")
            if not reopen and current_status_code not in {"CLOSED"}:
                raise ValidationError("Open period is only available from a closed fiscal period in this slice.")

    def _check_sensitive_action_permission(self, actor_user_id: int | None, action_code: str) -> None:
        _ = actor_user_id, action_code
        return

    def _require_fiscal_period_repository(self, session: Session | None) -> FiscalPeriodRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._fiscal_period_repository_factory(session)

    def _require_fiscal_year_repository(self, session: Session | None) -> FiscalYearRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._fiscal_year_repository_factory(session)

    def _require_company_exists(self, session: Session | None, company_id: int) -> None:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        company_repository = self._company_repository_factory(session)
        if company_repository.get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

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
        except Exception:  # noqa: BLE001 — audit must never break period control flow
            pass