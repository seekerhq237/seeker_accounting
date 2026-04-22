from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.accounting.reference_data.repositories.country_repository import CountryRepository
from seeker_accounting.modules.accounting.reference_data.repositories.currency_repository import CurrencyRepository
from seeker_accounting.modules.companies.dto.company_commands import CreateCompanyCommand
from seeker_accounting.modules.companies.dto.company_dto import CompanyDetailDTO, CompanyListItemDTO
from seeker_accounting.modules.companies.models.company import Company
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.companies.services.company_context_service import CompanyContextService
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
CountryRepositoryFactory = Callable[[Session], CountryRepository]
CurrencyRepositoryFactory = Callable[[Session], CurrencyRepository]


class SystemAdminCompanyService:
    """Privileged company lifecycle operations for the system-admin workflow."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        country_repository_factory: CountryRepositoryFactory,
        currency_repository_factory: CurrencyRepositoryFactory,
        company_context_service: CompanyContextService | None = None,
        audit_service: "AuditService | None" = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory
        self._country_repository_factory = country_repository_factory
        self._currency_repository_factory = currency_repository_factory
        self._company_context_service = company_context_service
        self._audit_service = audit_service

    def has_companies(self) -> bool:
        with self._unit_of_work_factory() as uow:
            company_repository = self._require_company_repository(uow.session)
            return bool(company_repository.list_all_for_admin())

    def list_all_for_admin(self) -> list[CompanyListItemDTO]:
        with self._unit_of_work_factory() as uow:
            company_repository = self._require_company_repository(uow.session)
            companies = company_repository.list_all_for_admin()
            return [self._to_company_list_item_dto(company) for company in companies]

    def get_company(self, company_id: int) -> CompanyDetailDTO:
        with self._unit_of_work_factory() as uow:
            company_repository = self._require_company_repository(uow.session)
            company = company_repository.get_by_id(company_id)
            if company is None:
                raise NotFoundError(f"Company with id {company_id} was not found.")
            return self._to_company_detail_dto(company)

    def create_company(self, command: CreateCompanyCommand) -> CompanyDetailDTO:
        normalized_legal_name = self._require_text(command.legal_name, "Legal name")
        normalized_display_name = self._require_text(command.display_name, "Display name")
        country_code = self._require_code(command.country_code, "Country")
        base_currency_code = self._require_code(command.base_currency_code, "Base currency")

        with self._unit_of_work_factory() as uow:
            company_repository = self._require_company_repository(uow.session)
            country_repository = self._require_country_repository(uow.session)
            currency_repository = self._require_currency_repository(uow.session)

            self._validate_company_references(
                country_repository=country_repository,
                currency_repository=currency_repository,
                country_code=country_code,
                base_currency_code=base_currency_code,
            )
            self._ensure_legal_name_is_unique(company_repository, normalized_legal_name)

            company = Company(
                legal_name=normalized_legal_name,
                display_name=normalized_display_name,
                registration_number=self._normalize_optional_text(command.registration_number),
                tax_identifier=self._normalize_optional_text(command.tax_identifier),
                phone=self._normalize_optional_text(command.phone),
                email=self._normalize_optional_text(command.email),
                website=self._normalize_optional_text(command.website),
                sector_of_operation=self._normalize_optional_text(command.sector_of_operation),
                address_line_1=self._normalize_optional_text(command.address_line_1),
                address_line_2=self._normalize_optional_text(command.address_line_2),
                city=self._normalize_optional_text(command.city),
                region=self._normalize_optional_text(command.region),
                country_code=country_code,
                base_currency_code=base_currency_code,
            )
            company_repository.add(company)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_company_integrity_error(exc) from exc

        from seeker_accounting.modules.audit.event_type_catalog import COMPANY_CREATED

        self._record_audit(company.id, COMPANY_CREATED, "Company", company.id, "Created company")
        return self._to_company_detail_dto(company)

    def deactivate_company(self, company_id: int) -> None:
        with self._unit_of_work_factory() as uow:
            company_repository = self._require_company_repository(uow.session)
            company = company_repository.get_by_id(company_id)
            if company is None:
                raise NotFoundError(f"Company with id {company_id} was not found.")

            company.is_active = False
            company_repository.save(company)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Company could not be deactivated.") from exc

        self._clear_active_company_if_selected(company_id)

    def reactivate_company(self, company_id: int) -> None:
        with self._unit_of_work_factory() as uow:
            company_repository = self._require_company_repository(uow.session)
            company = company_repository.get_by_id(company_id)
            if company is None:
                raise NotFoundError(f"Company with id {company_id} was not found.")
            if company.deleted_at is not None:
                raise ValidationError(
                    "This company is scheduled for deletion. Use restore_company_from_deletion instead."
                )

            company.is_active = True
            company_repository.save(company)
            uow.commit()

        from seeker_accounting.modules.audit.event_type_catalog import COMPANY_REACTIVATED

        self._record_audit(company_id, COMPANY_REACTIVATED, "Company", company_id, "Company reactivated")

    def schedule_company_deletion(self, company_id: int) -> None:
        from datetime import datetime, timezone

        with self._unit_of_work_factory() as uow:
            company_repository = self._require_company_repository(uow.session)
            company = company_repository.get_by_id(company_id)
            if company is None:
                raise NotFoundError(f"Company with id {company_id} was not found.")
            if company.deleted_at is not None:
                raise ValidationError("Company is already scheduled for deletion.")

            company.is_active = False
            company.deleted_at = datetime.now(timezone.utc)
            company_repository.save(company)
            uow.commit()

        self._clear_active_company_if_selected(company_id)

        from seeker_accounting.modules.audit.event_type_catalog import COMPANY_DELETION_SCHEDULED

        self._record_audit(
            company_id,
            COMPANY_DELETION_SCHEDULED,
            "Company",
            company_id,
            "Company scheduled for deletion",
        )

    def restore_company_from_deletion(self, company_id: int) -> None:
        with self._unit_of_work_factory() as uow:
            company_repository = self._require_company_repository(uow.session)
            company = company_repository.get_by_id(company_id)
            if company is None:
                raise NotFoundError(f"Company with id {company_id} was not found.")
            if company.deleted_at is None:
                raise ValidationError("Company is not in a pending-deletion state.")

            company.deleted_at = None
            company.is_active = True
            company_repository.save(company)
            uow.commit()

        from seeker_accounting.modules.audit.event_type_catalog import COMPANY_DELETION_RESTORED

        self._record_audit(
            company_id,
            COMPANY_DELETION_RESTORED,
            "Company",
            company_id,
            "Company deletion restored",
        )

    def _clear_active_company_if_selected(self, company_id: int) -> None:
        if self._company_context_service is None:
            return
        active_company = self._company_context_service.get_active_company()
        if active_company is not None and active_company.company_id == company_id:
            self._company_context_service.clear_active_company()

    def _require_company_repository(self, session: Session | None) -> CompanyRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._company_repository_factory(session)

    def _require_country_repository(self, session: Session | None) -> CountryRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._country_repository_factory(session)

    def _require_currency_repository(self, session: Session | None) -> CurrencyRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._currency_repository_factory(session)

    def _validate_company_references(
        self,
        country_repository: CountryRepository,
        currency_repository: CurrencyRepository,
        country_code: str,
        base_currency_code: str,
    ) -> None:
        if not country_repository.exists_active(country_code):
            raise ValidationError("Country must reference an existing active country.")
        if not currency_repository.exists_active(base_currency_code):
            raise ValidationError("Base currency must reference an existing active currency.")

    def _ensure_legal_name_is_unique(
        self,
        company_repository: CompanyRepository,
        legal_name: str,
        exclude_company_id: int | None = None,
    ) -> None:
        if company_repository.legal_name_exists(legal_name, exclude_company_id=exclude_company_id):
            raise ConflictError("A company with this legal name already exists.")

    def _translate_company_integrity_error(self, exc: IntegrityError) -> ValidationError | ConflictError:
        message = str(exc.orig).lower() if exc.orig is not None else str(exc).lower()
        if "legal_name" in message or "uq_companies_legal_name" in message or "unique" in message:
            return ConflictError("A company with this legal name already exists.")
        return ValidationError("Company data could not be saved.")

    def _require_text(self, value: str, label: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValidationError(f"{label} is required.")
        return normalized

    def _require_code(self, value: str, label: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValidationError(f"{label} is required.")
        return normalized

    def _normalize_optional_text(self, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    def _to_company_list_item_dto(self, company: Company) -> CompanyListItemDTO:
        return CompanyListItemDTO(
            id=company.id,
            legal_name=company.legal_name,
            display_name=company.display_name,
            country_code=company.country_code,
            base_currency_code=company.base_currency_code,
            logo_storage_path=company.logo_storage_path,
            is_active=company.is_active,
            updated_at=company.updated_at,
            deleted_at=company.deleted_at,
        )

    def _to_company_detail_dto(self, company: Company) -> CompanyDetailDTO:
        return CompanyDetailDTO(
            id=company.id,
            legal_name=company.legal_name,
            display_name=company.display_name,
            logo_storage_path=company.logo_storage_path,
            logo_original_filename=company.logo_original_filename,
            logo_content_type=company.logo_content_type,
            logo_updated_at=company.logo_updated_at,
            registration_number=company.registration_number,
            tax_identifier=company.tax_identifier,
            cnps_employer_number=company.cnps_employer_number,
            phone=company.phone,
            email=company.email,
            website=company.website,
            sector_of_operation=company.sector_of_operation,
            address_line_1=company.address_line_1,
            address_line_2=company.address_line_2,
            city=company.city,
            region=company.region,
            country_code=company.country_code,
            base_currency_code=company.base_currency_code,
            is_active=company.is_active,
            created_at=company.created_at,
            updated_at=company.updated_at,
            preferences=None,
            fiscal_defaults=None,
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
        from seeker_accounting.modules.audit.event_type_catalog import MODULE_COMPANIES

        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type_code,
                    module_code=MODULE_COMPANIES,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    description=description,
                ),
            )
        except Exception:
            return
