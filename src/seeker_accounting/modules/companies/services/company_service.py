from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.repositories.user_company_access_repository import (
    UserCompanyAccessRepository,
)
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.accounting.reference_data.repositories.country_repository import CountryRepository
from seeker_accounting.modules.accounting.reference_data.repositories.currency_repository import CurrencyRepository
from seeker_accounting.modules.companies.dto.company_commands import (
    CreateCompanyCommand,
    UpdateCompanyCommand,
    UpdateCompanyFiscalDefaultsCommand,
    UpdateCompanyPreferencesCommand,
)
from seeker_accounting.modules.companies.dto.company_dto import (
    CompanyDetailDTO,
    CompanyFiscalDefaultsDTO,
    CompanyListItemDTO,
    CompanyPreferencesDTO,
    ReferenceOptionDTO,
)
from seeker_accounting.modules.companies.models.company import Company
from seeker_accounting.modules.companies.models.company_fiscal_default import CompanyFiscalDefault
from seeker_accounting.modules.companies.models.company_preference import CompanyPreference
from seeker_accounting.modules.companies.repositories.company_fiscal_default_repository import (
    CompanyFiscalDefaultRepository,
)
from seeker_accounting.modules.companies.repositories.company_preference_repository import (
    CompanyPreferenceRepository,
)
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.companies.services.company_context_service import CompanyContextService
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, PermissionDeniedError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
CompanyPreferenceRepositoryFactory = Callable[[Session], CompanyPreferenceRepository]
CompanyFiscalDefaultRepositoryFactory = Callable[[Session], CompanyFiscalDefaultRepository]
CountryRepositoryFactory = Callable[[Session], CountryRepository]
CurrencyRepositoryFactory = Callable[[Session], CurrencyRepository]
UserCompanyAccessRepositoryFactory = Callable[[Session], UserCompanyAccessRepository]


class CompanyService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        company_preference_repository_factory: CompanyPreferenceRepositoryFactory,
        company_fiscal_default_repository_factory: CompanyFiscalDefaultRepositoryFactory,
        country_repository_factory: CountryRepositoryFactory,
        currency_repository_factory: CurrencyRepositoryFactory,
        company_context_service: CompanyContextService,
        user_company_access_repository_factory: UserCompanyAccessRepositoryFactory,
        permission_service: PermissionService,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory
        self._company_preference_repository_factory = company_preference_repository_factory
        self._company_fiscal_default_repository_factory = company_fiscal_default_repository_factory
        self._country_repository_factory = country_repository_factory
        self._currency_repository_factory = currency_repository_factory
        self._company_context_service = company_context_service
        self._user_company_access_repository_factory = user_company_access_repository_factory
        self._permission_service = permission_service
        self._audit_service = audit_service

    def list_companies(self) -> list[CompanyListItemDTO]:
        current_user_id = self._require_authenticated_user(
            "You must log in before viewing available organisations."
        )
        self._permission_service.require_any_permission(("companies.view", "companies.select_active"))
        return self.list_companies_for_user(current_user_id)

    def list_all_active_companies(self) -> list[CompanyListItemDTO]:
        """List all active companies without authentication.

        Used exclusively at the login screen before any user is authenticated,
        e.g. to populate the company picker for the ``admin`` alias flow.
        """
        with self._unit_of_work_factory() as uow:
            company_repository = self._require_company_repository(uow.session)
            companies = company_repository.list_active()
            return [self._to_company_list_item_dto(company) for company in companies]

    def list_companies_for_user(self, user_id: int) -> list[CompanyListItemDTO]:
        if user_id <= 0:
            return []
        if self._permission_service.has_authenticated_actor():
            current_user_id = self._permission_service.current_user_id
            if current_user_id != user_id:
                self._permission_service.require_any_permission(("companies.view", "companies.select_active"))

        with self._unit_of_work_factory() as uow:
            company_repository = self._require_company_repository(uow.session)
            companies = self._filter_companies_for_user_id(company_repository.list_active(), uow.session, user_id)
            return [self._to_company_list_item_dto(company) for company in companies]

    def list_available_countries(self) -> list[ReferenceOptionDTO]:
        with self._unit_of_work_factory() as uow:
            country_repository = self._require_country_repository(uow.session)
            countries = country_repository.list_active()
            return [ReferenceOptionDTO(code=country.code, name=country.name) for country in countries]

    def list_available_currencies(self) -> list[ReferenceOptionDTO]:
        with self._unit_of_work_factory() as uow:
            currency_repository = self._require_currency_repository(uow.session)
            currencies = currency_repository.list_active()
            return [ReferenceOptionDTO(code=currency.code, name=currency.name) for currency in currencies]

    def get_company(self, company_id: int) -> CompanyDetailDTO:
        self._permission_service.require_permission("companies.view")
        with self._unit_of_work_factory() as uow:
            company_repository = self._require_company_repository(uow.session)
            preference_repository = self._require_preference_repository(uow.session)
            fiscal_default_repository = self._require_fiscal_default_repository(uow.session)

            company = company_repository.get_by_id(company_id)
            if company is None:
                raise NotFoundError(f"Company with id {company_id} was not found.")
            self._ensure_company_access(uow.session, company.id)

            preferences = preference_repository.get_by_company_id(company_id)
            fiscal_defaults = fiscal_default_repository.get_by_company_id(company_id)
            return self._to_company_detail_dto(company, preferences, fiscal_defaults)

    def create_company(self, command: CreateCompanyCommand) -> CompanyDetailDTO:
        self._permission_service.require_permission("companies.create")
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
                cnps_employer_number=self._normalize_optional_text(command.cnps_employer_number),
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
            return self._to_company_detail_dto(company, None, None)

    def update_company(self, company_id: int, command: UpdateCompanyCommand) -> CompanyDetailDTO:
        self._permission_service.require_permission("companies.edit")
        normalized_legal_name = self._require_text(command.legal_name, "Legal name")
        normalized_display_name = self._require_text(command.display_name, "Display name")
        country_code = self._require_code(command.country_code, "Country")
        base_currency_code = self._require_code(command.base_currency_code, "Base currency")

        with self._unit_of_work_factory() as uow:
            company_repository = self._require_company_repository(uow.session)
            preference_repository = self._require_preference_repository(uow.session)
            fiscal_default_repository = self._require_fiscal_default_repository(uow.session)
            country_repository = self._require_country_repository(uow.session)
            currency_repository = self._require_currency_repository(uow.session)

            company = company_repository.get_by_id(company_id)
            if company is None:
                raise NotFoundError(f"Company with id {company_id} was not found.")
            self._ensure_company_access(uow.session, company.id)

            self._validate_company_references(
                country_repository=country_repository,
                currency_repository=currency_repository,
                country_code=country_code,
                base_currency_code=base_currency_code,
            )
            self._ensure_legal_name_is_unique(company_repository, normalized_legal_name, exclude_company_id=company_id)

            company.legal_name = normalized_legal_name
            company.display_name = normalized_display_name
            company.registration_number = self._normalize_optional_text(command.registration_number)
            company.tax_identifier = self._normalize_optional_text(command.tax_identifier)
            company.cnps_employer_number = self._normalize_optional_text(command.cnps_employer_number)
            company.phone = self._normalize_optional_text(command.phone)
            company.email = self._normalize_optional_text(command.email)
            company.website = self._normalize_optional_text(command.website)
            company.sector_of_operation = self._normalize_optional_text(command.sector_of_operation)
            company.address_line_1 = self._normalize_optional_text(command.address_line_1)
            company.address_line_2 = self._normalize_optional_text(command.address_line_2)
            company.city = self._normalize_optional_text(command.city)
            company.region = self._normalize_optional_text(command.region)
            company.country_code = country_code
            company.base_currency_code = base_currency_code
            company_repository.save(company)

            preferences = preference_repository.get_by_company_id(company_id)
            fiscal_defaults = fiscal_default_repository.get_by_company_id(company_id)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_company_integrity_error(exc) from exc

        active_company = self._company_context_service.get_active_company()
        if active_company is not None and active_company.company_id == company_id:
            self._company_context_service.set_active_company(company_id)

        from seeker_accounting.modules.audit.event_type_catalog import COMPANY_UPDATED
        self._record_audit(company_id, COMPANY_UPDATED, "Company", company.id, "Updated company")
        return self._to_company_detail_dto(company, preferences, fiscal_defaults)

    def update_company_preferences(
        self,
        company_id: int,
        command: UpdateCompanyPreferencesCommand,
    ) -> CompanyPreferencesDTO:
        self._permission_service.require_permission("companies.preferences.manage")
        date_format_code = self._require_text(command.date_format_code, "Date format")
        number_format_code = self._require_text(command.number_format_code, "Number format")
        if command.decimal_places < 0:
            raise ValidationError("Decimal places cannot be negative.")
        if command.idle_timeout_minutes < 1:
            raise ValidationError("Idle timeout must be at least 1 minute.")
        if command.password_expiry_days < 0:
            raise ValidationError("Password expiry days cannot be negative.")

        with self._unit_of_work_factory() as uow:
            company_repository = self._require_company_repository(uow.session)
            preference_repository = self._require_preference_repository(uow.session)

            company = company_repository.get_by_id(company_id)
            if company is None:
                raise NotFoundError(f"Company with id {company_id} was not found.")
            self._ensure_company_access(uow.session, company.id)

            preference = preference_repository.get_by_company_id(company_id)
            if preference is None:
                preference = CompanyPreference(
                    company_id=company_id,
                    date_format_code=date_format_code,
                    number_format_code=number_format_code,
                    decimal_places=command.decimal_places,
                    tax_inclusive_default=command.tax_inclusive_default,
                    allow_negative_stock=command.allow_negative_stock,
                    default_inventory_cost_method=self._normalize_optional_text(command.default_inventory_cost_method),
                    idle_timeout_minutes=command.idle_timeout_minutes,
                    password_expiry_days=command.password_expiry_days,
                )
                preference_repository.add(preference)
            else:
                preference.date_format_code = date_format_code
                preference.number_format_code = number_format_code
                preference.decimal_places = command.decimal_places
                preference.tax_inclusive_default = command.tax_inclusive_default
                preference.allow_negative_stock = command.allow_negative_stock
                preference.default_inventory_cost_method = self._normalize_optional_text(
                    command.default_inventory_cost_method
                )
                preference.idle_timeout_minutes = command.idle_timeout_minutes
                preference.password_expiry_days = command.password_expiry_days
                preference_repository.save(preference)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Company preferences could not be saved.") from exc

            return self._to_company_preferences_dto(preference)

    def get_company_preferences(self, company_id: int) -> CompanyPreferencesDTO:
        """Return effective company preferences, using defaults when no row exists."""
        self._permission_service.require_permission("companies.view")
        with self._unit_of_work_factory() as uow:
            company_repository = self._require_company_repository(uow.session)
            preference_repository = self._require_preference_repository(uow.session)

            company = company_repository.get_by_id(company_id)
            if company is None:
                raise NotFoundError(f"Company with id {company_id} was not found.")
            self._ensure_company_access(uow.session, company.id)

            preference = preference_repository.get_by_company_id(company_id)
            if preference is not None:
                return self._to_company_preferences_dto(preference)

            from datetime import datetime, timezone
            return CompanyPreferencesDTO(
                company_id=company_id,
                date_format_code="DMY_SLASH",
                number_format_code="SPACE_COMMA",
                decimal_places=2,
                tax_inclusive_default=False,
                allow_negative_stock=False,
                default_inventory_cost_method=None,
                idle_timeout_minutes=2,
                password_expiry_days=30,
                updated_at=datetime.now(timezone.utc),
            )

    def update_company_fiscal_defaults(
        self,
        company_id: int,
        command: UpdateCompanyFiscalDefaultsCommand,
    ) -> CompanyFiscalDefaultsDTO:
        self._permission_service.require_permission("companies.fiscal_defaults.manage")
        if not 1 <= command.fiscal_year_start_month <= 12:
            raise ValidationError("Fiscal year start month must be between 1 and 12.")
        if not 1 <= command.fiscal_year_start_day <= 31:
            raise ValidationError("Fiscal year start day must be between 1 and 31.")
        if command.default_posting_grace_days is not None and command.default_posting_grace_days < 0:
            raise ValidationError("Default posting grace days cannot be negative.")

        with self._unit_of_work_factory() as uow:
            company_repository = self._require_company_repository(uow.session)
            fiscal_default_repository = self._require_fiscal_default_repository(uow.session)

            company = company_repository.get_by_id(company_id)
            if company is None:
                raise NotFoundError(f"Company with id {company_id} was not found.")
            self._ensure_company_access(uow.session, company.id)

            fiscal_default = fiscal_default_repository.get_by_company_id(company_id)
            if fiscal_default is None:
                fiscal_default = CompanyFiscalDefault(
                    company_id=company_id,
                    fiscal_year_start_month=command.fiscal_year_start_month,
                    fiscal_year_start_day=command.fiscal_year_start_day,
                    default_posting_grace_days=command.default_posting_grace_days,
                )
                fiscal_default_repository.add(fiscal_default)
            else:
                fiscal_default.fiscal_year_start_month = command.fiscal_year_start_month
                fiscal_default.fiscal_year_start_day = command.fiscal_year_start_day
                fiscal_default.default_posting_grace_days = command.default_posting_grace_days
                fiscal_default_repository.save(fiscal_default)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Company fiscal defaults could not be saved.") from exc

            return self._to_company_fiscal_defaults_dto(fiscal_default)

    def deactivate_company(self, company_id: int) -> None:
        self._permission_service.require_permission("companies.deactivate")
        with self._unit_of_work_factory() as uow:
            company_repository = self._require_company_repository(uow.session)
            company = company_repository.get_by_id(company_id)
            if company is None:
                raise NotFoundError(f"Company with id {company_id} was not found.")
            self._ensure_company_access(uow.session, company.id)

            company.is_active = False
            company_repository.save(company)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Company could not be deactivated.") from exc

        active_company = self._company_context_service.get_active_company()
        if active_company is not None and active_company.company_id == company_id:
            self._company_context_service.clear_active_company()

    def reactivate_company(self, company_id: int) -> None:
        raise PermissionDeniedError(
            "Company reactivation is reserved for the system administrator workflow."
        )

    def schedule_company_deletion(self, company_id: int) -> None:
        raise PermissionDeniedError(
            "Company deletion scheduling is reserved for the system administrator workflow."
        )

    def restore_company_from_deletion(self, company_id: int) -> None:
        raise PermissionDeniedError(
            "Company restoration is reserved for the system administrator workflow."
        )

    def list_all_for_admin(self) -> list[CompanyListItemDTO]:
        raise PermissionDeniedError(
            "Full company administration is reserved for the system administrator workflow."
        )

    def _require_company_repository(self, session: Session | None) -> CompanyRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._company_repository_factory(session)

    def _require_preference_repository(self, session: Session | None) -> CompanyPreferenceRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._company_preference_repository_factory(session)

    def _require_fiscal_default_repository(self, session: Session | None) -> CompanyFiscalDefaultRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._company_fiscal_default_repository_factory(session)

    def _require_country_repository(self, session: Session | None) -> CountryRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._country_repository_factory(session)

    def _require_currency_repository(self, session: Session | None) -> CurrencyRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._currency_repository_factory(session)

    def _require_user_company_access_repository(
        self,
        session: Session | None,
    ) -> UserCompanyAccessRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._user_company_access_repository_factory(session)

    def _require_authenticated_user(self, message: str) -> int:
        current_user_id = self._permission_service.current_user_id
        if current_user_id is None:
            raise PermissionDeniedError(message)
        return current_user_id

    def _require_permission_if_authenticated(self, permission_code: str) -> None:
        if self._permission_service.has_authenticated_actor():
            self._permission_service.require_permission(permission_code)

    def _require_any_permission_if_authenticated(self, permission_codes: tuple[str, ...]) -> None:
        if self._permission_service.has_authenticated_actor():
            self._permission_service.require_any_permission(permission_codes)

    def _filter_companies_for_current_user(
        self,
        companies: list[Company],
        session: Session | None,
    ) -> list[Company]:
        current_user_id = self._permission_service.current_user_id
        if current_user_id is None:
            return companies
        return self._filter_companies_for_user_id(companies, session, current_user_id)

    def _filter_companies_for_user_id(
        self,
        companies: list[Company],
        session: Session | None,
        user_id: int,
    ) -> list[Company]:
        access_repository = self._require_user_company_access_repository(session)
        accessible_company_ids = {
            access.company_id for access in access_repository.list_by_user_id(user_id)
        }
        return [company for company in companies if company.id in accessible_company_ids]

    def _ensure_company_access(self, session: Session | None, company_id: int) -> None:
        current_user_id = self._permission_service.current_user_id
        if current_user_id is None:
            return
        access_repository = self._require_user_company_access_repository(session)
        if access_repository.get_by_user_and_company(current_user_id, company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

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

    def _to_company_detail_dto(
        self,
        company: Company,
        preference: CompanyPreference | None,
        fiscal_default: CompanyFiscalDefault | None,
    ) -> CompanyDetailDTO:
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
            preferences=self._to_company_preferences_dto(preference) if preference is not None else None,
            fiscal_defaults=(
                self._to_company_fiscal_defaults_dto(fiscal_default) if fiscal_default is not None else None
            ),
        )

    def _to_company_preferences_dto(self, preference: CompanyPreference) -> CompanyPreferencesDTO:
        return CompanyPreferencesDTO(
            company_id=preference.company_id,
            date_format_code=preference.date_format_code,
            number_format_code=preference.number_format_code,
            decimal_places=preference.decimal_places,
            tax_inclusive_default=preference.tax_inclusive_default,
            allow_negative_stock=preference.allow_negative_stock,
            default_inventory_cost_method=preference.default_inventory_cost_method,
            idle_timeout_minutes=preference.idle_timeout_minutes,
            password_expiry_days=preference.password_expiry_days,
            updated_at=preference.updated_at,
        )

    def _to_company_fiscal_defaults_dto(self, fiscal_default: CompanyFiscalDefault) -> CompanyFiscalDefaultsDTO:
        return CompanyFiscalDefaultsDTO(
            company_id=fiscal_default.company_id,
            fiscal_year_start_month=fiscal_default.fiscal_year_start_month,
            fiscal_year_start_day=fiscal_default.fiscal_year_start_day,
            default_posting_grace_days=fiscal_default.default_posting_grace_days,
            updated_at=fiscal_default.updated_at,
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
            pass  # Audit must not break business operations
