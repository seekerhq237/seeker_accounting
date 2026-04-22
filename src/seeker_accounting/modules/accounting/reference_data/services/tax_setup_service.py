from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.accounting.chart_of_accounts.models.account import Account
from seeker_accounting.modules.accounting.chart_of_accounts.repositories.account_repository import (
    AccountRepository,
)
from seeker_accounting.modules.accounting.reference_data.dto.tax_code_account_mapping_dto import (
    SetTaxCodeAccountMappingCommand,
    TaxCodeAccountMappingDTO,
)
from seeker_accounting.modules.accounting.reference_data.dto.tax_setup_dto import (
    CreateTaxCodeCommand,
    TaxCodeDTO,
    TaxCodeListItemDTO,
    UpdateTaxCodeCommand,
)
from seeker_accounting.modules.accounting.reference_data.models.tax_code_account_mapping import (
    TaxCodeAccountMapping,
)
from seeker_accounting.modules.accounting.reference_data.models.tax_code import TaxCode
from seeker_accounting.modules.accounting.reference_data.repositories.tax_code_account_mapping_repository import (
    TaxCodeAccountMappingRepository,
)
from seeker_accounting.modules.accounting.reference_data.repositories.tax_code_repository import TaxCodeRepository
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

TaxCodeRepositoryFactory = Callable[[Session], TaxCodeRepository]
TaxCodeAccountMappingRepositoryFactory = Callable[[Session], TaxCodeAccountMappingRepository]
AccountRepositoryFactory = Callable[[Session], AccountRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]


class TaxSetupService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        tax_code_repository_factory: TaxCodeRepositoryFactory,
        tax_code_account_mapping_repository_factory: TaxCodeAccountMappingRepositoryFactory,
        account_repository_factory: AccountRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        permission_service: PermissionService,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._tax_code_repository_factory = tax_code_repository_factory
        self._tax_code_account_mapping_repository_factory = tax_code_account_mapping_repository_factory
        self._account_repository_factory = account_repository_factory
        self._company_repository_factory = company_repository_factory
        self._permission_service = permission_service
        self._audit_service = audit_service

    def list_tax_codes(self, company_id: int, active_only: bool = False) -> list[TaxCodeListItemDTO]:
        self._permission_service.require_permission("reference.tax_codes.view")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_tax_code_repository(uow.session)
            rows = repository.list_by_company(company_id, active_only)
            return [self._to_tax_code_list_item_dto(row) for row in rows]

    def get_tax_code(self, company_id: int, tax_code_id: int) -> TaxCodeDTO:
        self._permission_service.require_permission("reference.tax_codes.view")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_tax_code_repository(uow.session)
            tax_code = repository.get_by_id(company_id, tax_code_id)
            if tax_code is None:
                raise NotFoundError(f"Tax code with id {tax_code_id} was not found.")
            return self._to_tax_code_dto(tax_code)

    def create_tax_code(self, company_id: int, command: CreateTaxCodeCommand) -> TaxCodeDTO:
        self._permission_service.require_permission("reference.tax_codes.create")
        normalized_code = self._require_code(command.code, "Tax code")
        normalized_name = self._require_text(command.name, "Tax code name")
        normalized_tax_type_code = self._require_code(command.tax_type_code, "Tax type code")
        normalized_calculation_method_code = self._require_code(
            command.calculation_method_code,
            "Calculation method code",
        )
        effective_from = self._require_date(command.effective_from, "Effective from")
        effective_to = command.effective_to
        if effective_to is not None and effective_to < effective_from:
            raise ValidationError("Effective to must be on or after effective from.")

        rate_percent = self._normalize_rate_percent(command.rate_percent, normalized_calculation_method_code)

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_tax_code_repository(uow.session)
            if repository.code_effective_from_exists(company_id, normalized_code, effective_from):
                raise ConflictError("A tax code with this code and effective date already exists for the company.")

            tax_code = TaxCode(
                company_id=company_id,
                code=normalized_code,
                name=normalized_name,
                tax_type_code=normalized_tax_type_code,
                calculation_method_code=normalized_calculation_method_code,
                rate_percent=rate_percent,
                is_recoverable=command.is_recoverable,
                effective_from=effective_from,
                effective_to=effective_to,
            )
            repository.add(tax_code)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_tax_code_integrity_error(exc) from exc

            from seeker_accounting.modules.audit.event_type_catalog import TAX_CODE_CREATED
            self._record_audit(company_id, TAX_CODE_CREATED, "TaxCode", tax_code.id, "Created tax code")
            return self._to_tax_code_dto(tax_code)

    def update_tax_code(self, company_id: int, tax_code_id: int, command: UpdateTaxCodeCommand) -> TaxCodeDTO:
        self._permission_service.require_permission("reference.tax_codes.edit")
        normalized_code = self._require_code(command.code, "Tax code")
        normalized_name = self._require_text(command.name, "Tax code name")
        normalized_tax_type_code = self._require_code(command.tax_type_code, "Tax type code")
        normalized_calculation_method_code = self._require_code(
            command.calculation_method_code,
            "Calculation method code",
        )
        effective_from = self._require_date(command.effective_from, "Effective from")
        effective_to = command.effective_to
        if effective_to is not None and effective_to < effective_from:
            raise ValidationError("Effective to must be on or after effective from.")

        rate_percent = self._normalize_rate_percent(command.rate_percent, normalized_calculation_method_code)

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_tax_code_repository(uow.session)
            tax_code = repository.get_by_id(company_id, tax_code_id)
            if tax_code is None:
                raise NotFoundError(f"Tax code with id {tax_code_id} was not found.")

            if repository.code_effective_from_exists(
                company_id,
                normalized_code,
                effective_from,
                exclude_tax_code_id=tax_code_id,
            ):
                raise ConflictError("A tax code with this code and effective date already exists for the company.")

            tax_code.code = normalized_code
            tax_code.name = normalized_name
            tax_code.tax_type_code = normalized_tax_type_code
            tax_code.calculation_method_code = normalized_calculation_method_code
            tax_code.rate_percent = rate_percent
            tax_code.is_recoverable = command.is_recoverable
            tax_code.effective_from = effective_from
            tax_code.effective_to = effective_to
            repository.save(tax_code)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_tax_code_integrity_error(exc) from exc

            from seeker_accounting.modules.audit.event_type_catalog import TAX_CODE_UPDATED
            self._record_audit(company_id, TAX_CODE_UPDATED, "TaxCode", tax_code.id, "Updated tax code")
            return self._to_tax_code_dto(tax_code)

    def deactivate_tax_code(self, company_id: int, tax_code_id: int) -> None:
        self._permission_service.require_permission("reference.tax_codes.deactivate")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_tax_code_repository(uow.session)
            tax_code = repository.get_by_id(company_id, tax_code_id)
            if tax_code is None:
                raise NotFoundError(f"Tax code with id {tax_code_id} was not found.")

            tax_code.is_active = False
            repository.save(tax_code)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Tax code could not be deactivated.") from exc

    def list_tax_code_account_mappings(self, company_id: int) -> list[TaxCodeAccountMappingDTO]:
        self._permission_service.require_permission("reference.tax_mappings.view")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            tax_code_repository = self._require_tax_code_repository(uow.session)
            mapping_repository = self._require_tax_code_account_mapping_repository(uow.session)
            account_repository = self._require_account_repository(uow.session)

            tax_codes = tax_code_repository.list_by_company(company_id, active_only=False)
            mappings_by_tax_code_id = {
                mapping.tax_code_id: mapping
                for mapping in mapping_repository.list_by_company(company_id)
            }
            accounts_by_id = {
                account.id: account
                for account in account_repository.list_by_company(company_id, active_only=False)
            }

            return [
                self._to_tax_code_account_mapping_dto(
                    tax_code=tax_code,
                    mapping=mappings_by_tax_code_id.get(tax_code.id),
                    accounts_by_id=accounts_by_id,
                )
                for tax_code in tax_codes
            ]

    def get_tax_code_account_mapping(self, company_id: int, tax_code_id: int) -> TaxCodeAccountMappingDTO:
        self._permission_service.require_permission("reference.tax_mappings.view")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            tax_code_repository = self._require_tax_code_repository(uow.session)
            mapping_repository = self._require_tax_code_account_mapping_repository(uow.session)
            account_repository = self._require_account_repository(uow.session)

            tax_code = tax_code_repository.get_by_id(company_id, tax_code_id)
            if tax_code is None:
                raise NotFoundError(f"Tax code with id {tax_code_id} was not found.")

            mapping = mapping_repository.get_by_tax_code(company_id, tax_code_id)
            accounts_by_id = {
                account.id: account
                for account in account_repository.list_by_company(company_id, active_only=False)
            }
            return self._to_tax_code_account_mapping_dto(
                tax_code=tax_code,
                mapping=mapping,
                accounts_by_id=accounts_by_id,
            )

    def set_tax_code_account_mapping(
        self,
        company_id: int,
        command: SetTaxCodeAccountMappingCommand,
    ) -> TaxCodeAccountMappingDTO:
        self._permission_service.require_permission("reference.tax_mappings.manage")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            tax_code_repository = self._require_tax_code_repository(uow.session)
            mapping_repository = self._require_tax_code_account_mapping_repository(uow.session)
            account_repository = self._require_account_repository(uow.session)

            tax_code = tax_code_repository.get_by_id(company_id, command.tax_code_id)
            if tax_code is None:
                raise NotFoundError(f"Tax code with id {command.tax_code_id} was not found.")

            sales_account = self._require_company_account(
                account_repository,
                company_id,
                command.sales_account_id,
                "Sales account",
            )
            purchase_account = self._require_company_account(
                account_repository,
                company_id,
                command.purchase_account_id,
                "Purchase account",
            )
            tax_liability_account = self._require_company_account(
                account_repository,
                company_id,
                command.tax_liability_account_id,
                "Tax liability account",
            )
            tax_asset_account = self._require_company_account(
                account_repository,
                company_id,
                command.tax_asset_account_id,
                "Tax asset account",
            )

            mapping = mapping_repository.get_by_tax_code(company_id, command.tax_code_id)
            if mapping is None:
                mapping = TaxCodeAccountMapping(
                    company_id=company_id,
                    tax_code_id=command.tax_code_id,
                    sales_account_id=sales_account.id if sales_account is not None else None,
                    purchase_account_id=purchase_account.id if purchase_account is not None else None,
                    tax_liability_account_id=(
                        tax_liability_account.id if tax_liability_account is not None else None
                    ),
                    tax_asset_account_id=tax_asset_account.id if tax_asset_account is not None else None,
                )
                mapping_repository.add(mapping)
            else:
                mapping.sales_account_id = sales_account.id if sales_account is not None else None
                mapping.purchase_account_id = purchase_account.id if purchase_account is not None else None
                mapping.tax_liability_account_id = (
                    tax_liability_account.id if tax_liability_account is not None else None
                )
                mapping.tax_asset_account_id = tax_asset_account.id if tax_asset_account is not None else None
                mapping_repository.save(mapping)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Tax code account mapping could not be saved.") from exc

            accounts_by_id = {
                account.id: account
                for account in account_repository.list_by_company(company_id, active_only=False)
            }
            return self._to_tax_code_account_mapping_dto(
                tax_code=tax_code,
                mapping=mapping,
                accounts_by_id=accounts_by_id,
            )

    def clear_tax_code_account_mapping(self, company_id: int, tax_code_id: int) -> None:
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            tax_code_repository = self._require_tax_code_repository(uow.session)
            mapping_repository = self._require_tax_code_account_mapping_repository(uow.session)

            if tax_code_repository.get_by_id(company_id, tax_code_id) is None:
                raise NotFoundError(f"Tax code with id {tax_code_id} was not found.")

            mapping = mapping_repository.get_by_tax_code(company_id, tax_code_id)
            if mapping is None:
                return

            mapping_repository.delete(mapping)
            uow.commit()

    def _require_tax_code_repository(self, session: Session | None) -> TaxCodeRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._tax_code_repository_factory(session)

    def _require_tax_code_account_mapping_repository(
        self,
        session: Session | None,
    ) -> TaxCodeAccountMappingRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._tax_code_account_mapping_repository_factory(session)

    def _require_account_repository(self, session: Session | None) -> AccountRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._account_repository_factory(session)

    def _require_company_exists(self, session: Session | None, company_id: int) -> None:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        company_repository = self._company_repository_factory(session)
        if company_repository.get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

    def _require_company_account(
        self,
        account_repository: AccountRepository,
        company_id: int,
        account_id: int | None,
        label: str,
    ) -> Account | None:
        if account_id is None:
            return None
        account = account_repository.get_by_id(company_id, account_id)
        if account is None:
            raise ValidationError(f"{label} must belong to the active company.")
        return account

    def _require_text(self, value: str, label: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValidationError(f"{label} is required.")
        return normalized

    def _require_code(self, value: str, label: str) -> str:
        return self._require_text(value, label).upper()

    def _require_date(self, value: date | None, label: str) -> date:
        if value is None:
            raise ValidationError(f"{label} is required.")
        return value

    def _normalize_rate_percent(self, value: Decimal | None, calculation_method_code: str) -> Decimal | None:
        if calculation_method_code == "PERCENTAGE":
            if value is None:
                raise ValidationError("Rate percent is required when calculation method is percentage.")
            if value < Decimal("0"):
                raise ValidationError("Rate percent cannot be negative.")
            return value

        if value is not None and value < Decimal("0"):
            raise ValidationError("Rate percent cannot be negative.")
        return value

    def _translate_tax_code_integrity_error(self, exc: IntegrityError) -> ValidationError | ConflictError:
        message = str(exc.orig).lower() if exc.orig is not None else str(exc).lower()
        if "unique" in message or "uq_tax_codes" in message:
            return ConflictError("A tax code with this code and effective date already exists for the company.")
        return ValidationError("Tax code data could not be saved.")

    def _to_tax_code_list_item_dto(self, row: TaxCode) -> TaxCodeListItemDTO:
        return TaxCodeListItemDTO(
            id=row.id,
            code=row.code,
            name=row.name,
            tax_type_code=row.tax_type_code,
            calculation_method_code=row.calculation_method_code,
            rate_percent=row.rate_percent,
            effective_from=row.effective_from,
            effective_to=row.effective_to,
            is_active=row.is_active,
        )

    def _to_tax_code_dto(self, row: TaxCode) -> TaxCodeDTO:
        return TaxCodeDTO(
            id=row.id,
            company_id=row.company_id,
            code=row.code,
            name=row.name,
            tax_type_code=row.tax_type_code,
            calculation_method_code=row.calculation_method_code,
            rate_percent=row.rate_percent,
            is_recoverable=row.is_recoverable,
            effective_from=row.effective_from,
            effective_to=row.effective_to,
            is_active=row.is_active,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _to_tax_code_account_mapping_dto(
        self,
        *,
        tax_code: TaxCode,
        mapping: TaxCodeAccountMapping | None,
        accounts_by_id: dict[int, Account],
    ) -> TaxCodeAccountMappingDTO:
        sales_account = accounts_by_id.get(mapping.sales_account_id) if mapping is not None else None
        purchase_account = accounts_by_id.get(mapping.purchase_account_id) if mapping is not None else None
        tax_liability_account = (
            accounts_by_id.get(mapping.tax_liability_account_id) if mapping is not None else None
        )
        tax_asset_account = accounts_by_id.get(mapping.tax_asset_account_id) if mapping is not None else None

        return TaxCodeAccountMappingDTO(
            tax_code_id=tax_code.id,
            tax_code_code=tax_code.code,
            tax_code_name=tax_code.name,
            sales_account_id=sales_account.id if sales_account is not None else None,
            sales_account_code=sales_account.account_code if sales_account is not None else None,
            sales_account_name=sales_account.account_name if sales_account is not None else None,
            purchase_account_id=purchase_account.id if purchase_account is not None else None,
            purchase_account_code=purchase_account.account_code if purchase_account is not None else None,
            purchase_account_name=purchase_account.account_name if purchase_account is not None else None,
            tax_liability_account_id=tax_liability_account.id if tax_liability_account is not None else None,
            tax_liability_account_code=(
                tax_liability_account.account_code if tax_liability_account is not None else None
            ),
            tax_liability_account_name=(
                tax_liability_account.account_name if tax_liability_account is not None else None
            ),
            tax_asset_account_id=tax_asset_account.id if tax_asset_account is not None else None,
            tax_asset_account_code=tax_asset_account.account_code if tax_asset_account is not None else None,
            tax_asset_account_name=tax_asset_account.account_name if tax_asset_account is not None else None,
            updated_at=mapping.updated_at if mapping is not None else None,
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
