from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.accounting.reference_data.dto.reference_data_dto import (
    AccountClassDTO,
    AccountTypeDTO,
    CreatePaymentTermCommand,
    PaymentTermDTO,
    PaymentTermListItemDTO,
    ReferenceOptionDTO,
    UpdatePaymentTermCommand,
)
from seeker_accounting.modules.accounting.reference_data.models.account_class import AccountClass
from seeker_accounting.modules.accounting.reference_data.models.account_type import AccountType
from seeker_accounting.modules.accounting.reference_data.models.payment_term import PaymentTerm
from seeker_accounting.modules.accounting.reference_data.repositories.account_class_repository import (
    AccountClassRepository,
)
from seeker_accounting.modules.accounting.reference_data.repositories.account_type_repository import (
    AccountTypeRepository,
)
from seeker_accounting.modules.accounting.reference_data.repositories.country_repository import CountryRepository
from seeker_accounting.modules.accounting.reference_data.repositories.currency_repository import CurrencyRepository
from seeker_accounting.modules.accounting.reference_data.repositories.payment_term_repository import (
    PaymentTermRepository,
)
from seeker_accounting.modules.accounting.reference_data.seeds.global_reference_data_seed import (
    GlobalReferenceSeedResult,
    ensure_global_reference_data_seed,
)
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

CountryRepositoryFactory = Callable[[Session], CountryRepository]
CurrencyRepositoryFactory = Callable[[Session], CurrencyRepository]
AccountClassRepositoryFactory = Callable[[Session], AccountClassRepository]
AccountTypeRepositoryFactory = Callable[[Session], AccountTypeRepository]
PaymentTermRepositoryFactory = Callable[[Session], PaymentTermRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]


class ReferenceDataService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        country_repository_factory: CountryRepositoryFactory,
        currency_repository_factory: CurrencyRepositoryFactory,
        account_class_repository_factory: AccountClassRepositoryFactory,
        account_type_repository_factory: AccountTypeRepositoryFactory,
        payment_term_repository_factory: PaymentTermRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        permission_service: PermissionService,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._country_repository_factory = country_repository_factory
        self._currency_repository_factory = currency_repository_factory
        self._account_class_repository_factory = account_class_repository_factory
        self._account_type_repository_factory = account_type_repository_factory
        self._payment_term_repository_factory = payment_term_repository_factory
        self._company_repository_factory = company_repository_factory
        self._permission_service = permission_service
        self._audit_service = audit_service

    def list_active_currencies(self) -> list[ReferenceOptionDTO]:
        with self._unit_of_work_factory() as uow:
            repository = self._require_currency_repository(uow.session)
            return [ReferenceOptionDTO(code=row.code, name=row.name) for row in repository.list_active()]

    def list_active_countries(self) -> list[ReferenceOptionDTO]:
        with self._unit_of_work_factory() as uow:
            repository = self._require_country_repository(uow.session)
            return [ReferenceOptionDTO(code=row.code, name=row.name) for row in repository.list_active()]

    def ensure_global_reference_data_seed(self) -> GlobalReferenceSeedResult:
        """Idempotently seed all countries and currencies from built-in CSV assets."""
        with self._unit_of_work_factory() as uow:
            session = uow.session
            if session is None:
                raise RuntimeError("Unit of work has no active session.")
            result = ensure_global_reference_data_seed(
                self._country_repository_factory(session),
                self._currency_repository_factory(session),
            )
            if result.countries_inserted or result.currencies_inserted:
                uow.commit()
            return result

    def list_account_classes(self, active_only: bool = True) -> list[AccountClassDTO]:
        with self._unit_of_work_factory() as uow:
            repository = self._require_account_class_repository(uow.session)
            return [self._to_account_class_dto(row) for row in repository.list_all(active_only=active_only)]

    def list_account_types(self, active_only: bool = True) -> list[AccountTypeDTO]:
        with self._unit_of_work_factory() as uow:
            repository = self._require_account_type_repository(uow.session)
            return [self._to_account_type_dto(row) for row in repository.list_all(active_only=active_only)]

    def list_payment_terms(self, company_id: int, active_only: bool = False) -> list[PaymentTermListItemDTO]:
        self._permission_service.require_permission("reference.payment_terms.view")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_payment_term_repository(uow.session)
            rows = repository.list_by_company(company_id, active_only)
            return [self._to_payment_term_list_item_dto(row) for row in rows]

    def get_payment_term(self, company_id: int, payment_term_id: int) -> PaymentTermDTO:
        self._permission_service.require_permission("reference.payment_terms.view")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_payment_term_repository(uow.session)
            payment_term = repository.get_by_id(company_id, payment_term_id)
            if payment_term is None:
                raise NotFoundError(f"Payment term with id {payment_term_id} was not found.")
            return self._to_payment_term_dto(payment_term)

    def create_payment_term(self, company_id: int, command: CreatePaymentTermCommand) -> PaymentTermDTO:
        self._permission_service.require_permission("reference.payment_terms.create")
        normalized_code = self._require_code(command.code, "Payment term code")
        normalized_name = self._require_text(command.name, "Payment term name")
        normalized_description = self._normalize_optional_text(command.description)
        if command.days_due < 0:
            raise ValidationError("Payment term days due cannot be negative.")

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_payment_term_repository(uow.session)

            if repository.code_exists(company_id, normalized_code):
                raise ConflictError("A payment term with this code already exists for the company.")
            if repository.name_exists(company_id, normalized_name):
                raise ConflictError("A payment term with this name already exists for the company.")

            payment_term = PaymentTerm(
                company_id=company_id,
                code=normalized_code,
                name=normalized_name,
                days_due=command.days_due,
                description=normalized_description,
            )
            repository.add(payment_term)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_payment_term_integrity_error(exc) from exc

            from seeker_accounting.modules.audit.event_type_catalog import PAYMENT_TERM_CREATED
            self._record_audit(company_id, PAYMENT_TERM_CREATED, "PaymentTerm", payment_term.id, "Created payment term")
            return self._to_payment_term_dto(payment_term)

    def update_payment_term(
        self,
        company_id: int,
        payment_term_id: int,
        command: UpdatePaymentTermCommand,
    ) -> PaymentTermDTO:
        self._permission_service.require_permission("reference.payment_terms.edit")
        normalized_code = self._require_code(command.code, "Payment term code")
        normalized_name = self._require_text(command.name, "Payment term name")
        normalized_description = self._normalize_optional_text(command.description)
        if command.days_due < 0:
            raise ValidationError("Payment term days due cannot be negative.")

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_payment_term_repository(uow.session)
            payment_term = repository.get_by_id(company_id, payment_term_id)
            if payment_term is None:
                raise NotFoundError(f"Payment term with id {payment_term_id} was not found.")

            if repository.code_exists(company_id, normalized_code, exclude_payment_term_id=payment_term_id):
                raise ConflictError("A payment term with this code already exists for the company.")
            if repository.name_exists(company_id, normalized_name, exclude_payment_term_id=payment_term_id):
                raise ConflictError("A payment term with this name already exists for the company.")

            payment_term.code = normalized_code
            payment_term.name = normalized_name
            payment_term.days_due = command.days_due
            payment_term.description = normalized_description
            repository.save(payment_term)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_payment_term_integrity_error(exc) from exc

            from seeker_accounting.modules.audit.event_type_catalog import PAYMENT_TERM_UPDATED
            self._record_audit(company_id, PAYMENT_TERM_UPDATED, "PaymentTerm", payment_term.id, "Updated payment term")
            return self._to_payment_term_dto(payment_term)

    def deactivate_payment_term(self, company_id: int, payment_term_id: int) -> None:
        self._permission_service.require_permission("reference.payment_terms.deactivate")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_payment_term_repository(uow.session)
            payment_term = repository.get_by_id(company_id, payment_term_id)
            if payment_term is None:
                raise NotFoundError(f"Payment term with id {payment_term_id} was not found.")

            payment_term.is_active = False
            repository.save(payment_term)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Payment term could not be deactivated.") from exc

    def _require_country_repository(self, session: Session | None) -> CountryRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._country_repository_factory(session)

    def _require_currency_repository(self, session: Session | None) -> CurrencyRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._currency_repository_factory(session)

    def _require_account_class_repository(self, session: Session | None) -> AccountClassRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._account_class_repository_factory(session)

    def _require_account_type_repository(self, session: Session | None) -> AccountTypeRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._account_type_repository_factory(session)

    def _require_payment_term_repository(self, session: Session | None) -> PaymentTermRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._payment_term_repository_factory(session)

    def _require_company_exists(self, session: Session | None, company_id: int) -> None:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        company_repository = self._company_repository_factory(session)
        if company_repository.get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

    def _require_text(self, value: str, label: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValidationError(f"{label} is required.")
        return normalized

    def _require_code(self, value: str, label: str) -> str:
        return self._require_text(value, label).upper()

    def _normalize_optional_text(self, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    def _translate_payment_term_integrity_error(self, exc: IntegrityError) -> ValidationError | ConflictError:
        message = str(exc.orig).lower() if exc.orig is not None else str(exc).lower()
        if "unique" in message or "uq_payment_terms" in message:
            return ConflictError("A payment term with this code or name already exists for the company.")
        return ValidationError("Payment term data could not be saved.")

    def _to_account_class_dto(self, row: AccountClass) -> AccountClassDTO:
        return AccountClassDTO(
            id=row.id,
            code=row.code,
            name=row.name,
            display_order=row.display_order,
            is_active=row.is_active,
        )

    def _to_account_type_dto(self, row: AccountType) -> AccountTypeDTO:
        return AccountTypeDTO(
            id=row.id,
            code=row.code,
            name=row.name,
            normal_balance=row.normal_balance,
            financial_statement_section_code=row.financial_statement_section_code,
            is_active=row.is_active,
        )

    def _to_payment_term_list_item_dto(self, row: PaymentTerm) -> PaymentTermListItemDTO:
        return PaymentTermListItemDTO(
            id=row.id,
            code=row.code,
            name=row.name,
            days_due=row.days_due,
            is_active=row.is_active,
        )

    def _to_payment_term_dto(self, row: PaymentTerm) -> PaymentTermDTO:
        return PaymentTermDTO(
            id=row.id,
            company_id=row.company_id,
            code=row.code,
            name=row.name,
            days_due=row.days_due,
            description=row.description,
            is_active=row.is_active,
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
        from seeker_accounting.modules.audit.event_type_catalog import MODULE_REFERENCE_DATA
        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type_code,
                    module_code=MODULE_REFERENCE_DATA,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    description=description,
                ),
            )
        except Exception:
            pass  # Audit must not break business operations
