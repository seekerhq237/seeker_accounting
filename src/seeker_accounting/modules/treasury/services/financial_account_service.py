from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.accounting.chart_of_accounts.models.account import Account
from seeker_accounting.modules.accounting.chart_of_accounts.repositories.account_repository import (
    AccountRepository,
)
from seeker_accounting.modules.accounting.reference_data.models.currency import Currency
from seeker_accounting.modules.accounting.reference_data.repositories.currency_repository import CurrencyRepository
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.treasury.dto.financial_account_commands import (
    CreateFinancialAccountCommand,
    UpdateFinancialAccountCommand,
)
from seeker_accounting.modules.treasury.dto.financial_account_dto import (
    FinancialAccountDetailDTO,
    FinancialAccountListItemDTO,
)
from seeker_accounting.modules.treasury.models.financial_account import FinancialAccount
from seeker_accounting.modules.treasury.repositories.financial_account_repository import (
    FinancialAccountRepository,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
AccountRepositoryFactory = Callable[[Session], AccountRepository]
CurrencyRepositoryFactory = Callable[[Session], CurrencyRepository]
FinancialAccountRepositoryFactory = Callable[[Session], FinancialAccountRepository]

_ALLOWED_FINANCIAL_ACCOUNT_TYPE_CODES = {"bank", "cash", "petty_cash"}


class FinancialAccountService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        account_repository_factory: AccountRepositoryFactory,
        currency_repository_factory: CurrencyRepositoryFactory,
        financial_account_repository_factory: FinancialAccountRepositoryFactory,
        permission_service: PermissionService,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory
        self._account_repository_factory = account_repository_factory
        self._currency_repository_factory = currency_repository_factory
        self._financial_account_repository_factory = financial_account_repository_factory
        self._permission_service = permission_service
        self._audit_service = audit_service

    def list_financial_accounts(self, company_id: int, active_only: bool = False) -> list[FinancialAccountListItemDTO]:
        self._permission_service.require_permission("treasury.financial_accounts.view")
        with self._unit_of_work_factory() as uow:
            company = self._require_company_exists(uow.session, company_id)
            repository = self._require_financial_account_repository(uow.session)
            rows = repository.list_by_company(company_id, active_only=active_only)
            return [self._to_list_item_dto(row) for row in rows]

    def get_financial_account(self, company_id: int, financial_account_id: int) -> FinancialAccountDetailDTO:
        self._permission_service.require_permission("treasury.financial_accounts.view")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_financial_account_repository(uow.session)
            financial_account = repository.get_by_id(company_id, financial_account_id)
            if financial_account is None:
                raise NotFoundError(f"Financial account with id {financial_account_id} was not found.")
            return self._to_detail_dto(financial_account)

    def create_financial_account(
        self,
        company_id: int,
        command: CreateFinancialAccountCommand,
    ) -> FinancialAccountDetailDTO:
        self._permission_service.require_permission("treasury.financial_accounts.create")
        normalized_command = self._normalize_create_command(command)

        with self._unit_of_work_factory() as uow:
            company = self._require_company_exists(uow.session, company_id)
            account_repository = self._require_account_repository(uow.session)
            currency_repository = self._require_currency_repository(uow.session)
            financial_account_repository = self._require_financial_account_repository(uow.session)

            if financial_account_repository.account_code_exists(company_id, normalized_command.account_code):
                raise ConflictError("A financial account with this code already exists for the company.")

            gl_account = self._require_gl_account(account_repository, company_id, normalized_command.gl_account_id)
            self._require_currency(currency_repository, company, normalized_command.currency_code)

            financial_account = FinancialAccount(
                company_id=company_id,
                account_code=normalized_command.account_code,
                name=normalized_command.name,
                financial_account_type_code=normalized_command.financial_account_type_code,
                gl_account_id=gl_account.id,
                bank_name=normalized_command.bank_name,
                bank_account_number=normalized_command.bank_account_number,
                bank_branch=normalized_command.bank_branch,
                currency_code=normalized_command.currency_code,
            )
            financial_account_repository.add(financial_account)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_integrity_error(exc) from exc

            from seeker_accounting.modules.audit.event_type_catalog import FINANCIAL_ACCOUNT_CREATED
            self._record_audit(company_id, FINANCIAL_ACCOUNT_CREATED, "FinancialAccount", financial_account.id, "Created financial account")
            return self.get_financial_account(company_id, financial_account.id)

    def update_financial_account(
        self,
        company_id: int,
        financial_account_id: int,
        command: UpdateFinancialAccountCommand,
    ) -> FinancialAccountDetailDTO:
        self._permission_service.require_permission("treasury.financial_accounts.edit")
        normalized_command = self._normalize_update_command(command)

        with self._unit_of_work_factory() as uow:
            company = self._require_company_exists(uow.session, company_id)
            account_repository = self._require_account_repository(uow.session)
            currency_repository = self._require_currency_repository(uow.session)
            financial_account_repository = self._require_financial_account_repository(uow.session)

            financial_account = financial_account_repository.get_by_id(company_id, financial_account_id)
            if financial_account is None:
                raise NotFoundError(f"Financial account with id {financial_account_id} was not found.")

            if financial_account_repository.account_code_exists(
                company_id,
                normalized_command.account_code,
                exclude_financial_account_id=financial_account_id,
            ):
                raise ConflictError("A financial account with this code already exists for the company.")

            gl_account = self._require_gl_account(account_repository, company_id, normalized_command.gl_account_id)
            self._require_currency(currency_repository, company, normalized_command.currency_code)

            financial_account.account_code = normalized_command.account_code
            financial_account.name = normalized_command.name
            financial_account.financial_account_type_code = normalized_command.financial_account_type_code
            financial_account.gl_account_id = gl_account.id
            financial_account.bank_name = normalized_command.bank_name
            financial_account.bank_account_number = normalized_command.bank_account_number
            financial_account.bank_branch = normalized_command.bank_branch
            financial_account.currency_code = normalized_command.currency_code
            financial_account.is_active = normalized_command.is_active
            financial_account_repository.save(financial_account)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_integrity_error(exc) from exc

            from seeker_accounting.modules.audit.event_type_catalog import FINANCIAL_ACCOUNT_UPDATED
            self._record_audit(company_id, FINANCIAL_ACCOUNT_UPDATED, "FinancialAccount", financial_account.id, "Updated financial account")
            return self.get_financial_account(company_id, financial_account.id)

    def deactivate_financial_account(self, company_id: int, financial_account_id: int) -> None:
        self._permission_service.require_permission("treasury.financial_accounts.deactivate")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_financial_account_repository(uow.session)
            financial_account = repository.get_by_id(company_id, financial_account_id)
            if financial_account is None:
                raise NotFoundError(f"Financial account with id {financial_account_id} was not found.")

            financial_account.is_active = False
            repository.save(financial_account)
            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Financial account could not be deactivated.") from exc

    def _normalize_create_command(self, command: CreateFinancialAccountCommand) -> CreateFinancialAccountCommand:
        return CreateFinancialAccountCommand(
            account_code=self._require_account_code(command.account_code),
            name=self._require_text(command.name, "Financial account name"),
            financial_account_type_code=self._require_type_code(command.financial_account_type_code),
            gl_account_id=self._require_positive_id(command.gl_account_id, "GL account"),
            currency_code=self._require_currency_code(command.currency_code),
            bank_name=self._normalize_optional_text(command.bank_name),
            bank_account_number=self._normalize_optional_text(command.bank_account_number),
            bank_branch=self._normalize_optional_text(command.bank_branch),
        )

    def _normalize_update_command(self, command: UpdateFinancialAccountCommand) -> UpdateFinancialAccountCommand:
        return UpdateFinancialAccountCommand(
            account_code=self._require_account_code(command.account_code),
            name=self._require_text(command.name, "Financial account name"),
            financial_account_type_code=self._require_type_code(command.financial_account_type_code),
            gl_account_id=self._require_positive_id(command.gl_account_id, "GL account"),
            currency_code=self._require_currency_code(command.currency_code),
            bank_name=self._normalize_optional_text(command.bank_name),
            bank_account_number=self._normalize_optional_text(command.bank_account_number),
            bank_branch=self._normalize_optional_text(command.bank_branch),
            is_active=bool(command.is_active),
        )

    def _require_company_exists(self, session: Session | None, company_id: int):
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        repository = self._company_repository_factory(session)
        company = repository.get_by_id(company_id)
        if company is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")
        return company

    def _require_financial_account_repository(self, session: Session | None) -> FinancialAccountRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._financial_account_repository_factory(session)

    def _require_account_repository(self, session: Session | None) -> AccountRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._account_repository_factory(session)

    def _require_currency_repository(self, session: Session | None) -> CurrencyRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._currency_repository_factory(session)

    def _require_gl_account(
        self,
        account_repository: AccountRepository,
        company_id: int,
        account_id: int,
    ) -> Account:
        account = account_repository.get_by_id(company_id, account_id)
        if account is None:
            raise ValidationError("GL account must belong to the active company.")
        if not account.is_active:
            raise ValidationError("GL account must be active.")
        return account

    def _require_currency(
        self,
        currency_repository: CurrencyRepository,
        company: object,
        currency_code: str,
    ) -> Currency:
        company_base_currency_code = getattr(company, "base_currency_code", None)
        if company_base_currency_code == currency_code:
            with self._unit_of_work_factory() as uow:
                session = uow.session
                if session is None:
                    raise RuntimeError("Unit of work has no active session.")
                currency = session.get(Currency, currency_code)
                if currency is None:
                    raise ValidationError("Currency must exist in the reference data.")
                return currency

        with self._unit_of_work_factory() as uow:
            session = uow.session
            if session is None:
                raise RuntimeError("Unit of work has no active session.")
            currency = session.get(Currency, currency_code)
            if currency is None or not currency.is_active:
                raise ValidationError("Currency must reference an active currency code.")
            return currency

    def _require_currency_code(self, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValidationError("Currency code is required.")
        return normalized

    def _require_type_code(self, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValidationError("Financial account type code is required.")
        if normalized not in _ALLOWED_FINANCIAL_ACCOUNT_TYPE_CODES:
            raise ValidationError("Financial account type code is not recognized.")
        return normalized

    def _require_account_code(self, value: str) -> str:
        normalized = "".join(character for character in value.strip().upper() if character not in {" ", "\t"})
        if not normalized:
            raise ValidationError("Financial account code is required.")
        return normalized

    def _require_text(self, value: str, label: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValidationError(f"{label} is required.")
        return normalized

    def _normalize_optional_text(self, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    def _require_positive_id(self, value: int, label: str) -> int:
        if value <= 0:
            raise ValidationError(f"{label} is required.")
        return value

    def _translate_integrity_error(self, exc: IntegrityError) -> ValidationError | ConflictError:
        message = str(exc.orig).lower() if exc.orig is not None else str(exc).lower()
        if "unique" in message or "uq_financial_accounts" in message:
            return ConflictError("A financial account with this code already exists for the company.")
        return ValidationError("Financial account data could not be saved.")

    def _to_list_item_dto(self, row: FinancialAccount) -> FinancialAccountListItemDTO:
        gl_account = row.gl_account
        return FinancialAccountListItemDTO(
            id=row.id,
            company_id=row.company_id,
            account_code=row.account_code,
            name=row.name,
            financial_account_type_code=row.financial_account_type_code,
            gl_account_id=row.gl_account_id,
            gl_account_code=gl_account.account_code if gl_account is not None else "",
            gl_account_name=gl_account.account_name if gl_account is not None else "",
            currency_code=row.currency_code,
            is_active=row.is_active,
            updated_at=row.updated_at,
        )

    def _to_detail_dto(self, row: FinancialAccount) -> FinancialAccountDetailDTO:
        gl_account = row.gl_account
        return FinancialAccountDetailDTO(
            id=row.id,
            company_id=row.company_id,
            account_code=row.account_code,
            name=row.name,
            financial_account_type_code=row.financial_account_type_code,
            gl_account_id=row.gl_account_id,
            gl_account_code=gl_account.account_code if gl_account is not None else "",
            gl_account_name=gl_account.account_name if gl_account is not None else "",
            currency_code=row.currency_code,
            bank_name=row.bank_name,
            bank_account_number=row.bank_account_number,
            bank_branch=row.bank_branch,
            is_active=row.is_active,
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
    ) -> None:
        if self._audit_service is None:
            return
        from seeker_accounting.modules.audit.dto.audit_event_dto import RecordAuditEventCommand
        from seeker_accounting.modules.audit.event_type_catalog import MODULE_TREASURY
        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type_code,
                    module_code=MODULE_TREASURY,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    description=description,
                ),
            )
        except Exception:
            pass  # Audit must not break business operations
