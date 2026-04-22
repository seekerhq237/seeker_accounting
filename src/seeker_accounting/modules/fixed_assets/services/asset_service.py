from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.fixed_assets.dto.asset_commands import CreateAssetCommand, UpdateAssetCommand
from seeker_accounting.modules.fixed_assets.dto.asset_dto import AssetDetailDTO, AssetListItemDTO
from seeker_accounting.modules.fixed_assets.models.asset import Asset
from seeker_accounting.modules.fixed_assets.repositories.asset_category_repository import AssetCategoryRepository
from seeker_accounting.modules.fixed_assets.repositories.asset_repository import AssetRepository
from seeker_accounting.modules.suppliers.repositories.supplier_repository import SupplierRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

VALID_DEPRECIATION_METHODS = frozenset({
    "straight_line",
    "declining_balance",
    "double_declining_balance",
    "declining_balance_150",
    "reducing_balance",            # backward-compatible alias for double_declining_balance
    "sum_of_years_digits",
    "units_of_production",
    "component",
    "group",
    "composite",
    "depletion",
    "annuity",
    "sinking_fund",
    "macrs",
    "amortization",
})
VALID_STATUS_CODES = frozenset({"draft", "active", "fully_depreciated", "disposed"})

AssetRepositoryFactory = Callable[[Session], AssetRepository]
AssetCategoryRepositoryFactory = Callable[[Session], AssetCategoryRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
SupplierRepositoryFactory = Callable[[Session], SupplierRepository]


class AssetService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        asset_repository_factory: AssetRepositoryFactory,
        asset_category_repository_factory: AssetCategoryRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        supplier_repository_factory: SupplierRepositoryFactory,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._asset_repository_factory = asset_repository_factory
        self._asset_category_repository_factory = asset_category_repository_factory
        self._company_repository_factory = company_repository_factory
        self._supplier_repository_factory = supplier_repository_factory
        self._audit_service = audit_service

    def list_assets(
        self,
        company_id: int,
        active_only: bool = False,
        query: str | None = None,
        status_code: str | None = None,
    ) -> list[AssetListItemDTO]:
        with self._unit_of_work_factory() as uow:
            repo = self._asset_repository_factory(uow.session)
            rows = repo.list_by_company(
                company_id, active_only=active_only, query=query, status_code=status_code
            )
            return [self._to_list_item_dto(r) for r in rows]

    def get_asset(self, company_id: int, asset_id: int) -> AssetDetailDTO:
        with self._unit_of_work_factory() as uow:
            repo = self._asset_repository_factory(uow.session)
            asset = repo.get_by_id(company_id, asset_id)
            if asset is None:
                raise NotFoundError(f"Asset {asset_id} not found.")
            return self._to_detail_dto(asset)

    def create_asset(self, company_id: int, command: CreateAssetCommand) -> AssetDetailDTO:
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            self._validate_asset_fields(command.asset_number, command.asset_name,
                                        command.acquisition_cost, command.salvage_value,
                                        command.useful_life_months,
                                        command.depreciation_method_code)
            if command.capitalization_date < command.acquisition_date:
                raise ValidationError("Capitalization date must be on or after acquisition date.")

            asset_repo = self._asset_repository_factory(uow.session)
            if asset_repo.get_by_number(company_id, command.asset_number) is not None:
                raise ConflictError(f"Asset number '{command.asset_number}' already exists for this company.")

            cat_repo = self._asset_category_repository_factory(uow.session)
            cat = cat_repo.get_by_id(company_id, command.asset_category_id)
            if cat is None or cat.company_id != company_id:
                raise ValidationError(f"Asset category {command.asset_category_id} not found in this company.")
            if not cat.is_active:
                raise ValidationError("Selected asset category is inactive.")

            if command.supplier_id is not None:
                self._validate_supplier(uow.session, company_id, command.supplier_id)

            asset = Asset(
                company_id=company_id,
                asset_number=command.asset_number.strip(),
                asset_name=command.asset_name.strip(),
                asset_category_id=command.asset_category_id,
                acquisition_date=command.acquisition_date,
                capitalization_date=command.capitalization_date,
                acquisition_cost=command.acquisition_cost,
                salvage_value=command.salvage_value,
                useful_life_months=command.useful_life_months,
                depreciation_method_code=command.depreciation_method_code,
                status_code="draft",
                supplier_id=command.supplier_id,
                purchase_bill_id=command.purchase_bill_id,
                notes=command.notes,
            )
            asset_repo.save(asset)
            uow.commit()
            # Reload with category for DTO
            asset = asset_repo.get_by_id(company_id, asset.id)
            from seeker_accounting.modules.audit.event_type_catalog import ASSET_CREATED
            self._record_audit(company_id, ASSET_CREATED, "Asset", asset.id, "Created fixed asset")
            return self._to_detail_dto(asset)

    def update_asset(
        self, company_id: int, asset_id: int, command: UpdateAssetCommand
    ) -> AssetDetailDTO:
        with self._unit_of_work_factory() as uow:
            asset_repo = self._asset_repository_factory(uow.session)
            asset = asset_repo.get_by_id(company_id, asset_id)
            if asset is None:
                raise NotFoundError(f"Asset {asset_id} not found.")

            # Immutability guard: posted assets may not have financial fields changed
            if asset.status_code in ("fully_depreciated", "disposed"):
                raise ValidationError(
                    f"Assets with status '{asset.status_code}' cannot be edited."
                )

            self._validate_asset_fields(command.asset_number, command.asset_name,
                                        command.acquisition_cost, command.salvage_value,
                                        command.useful_life_months,
                                        command.depreciation_method_code)
            if command.capitalization_date < command.acquisition_date:
                raise ValidationError("Capitalization date must be on or after acquisition date.")
            if command.status_code not in VALID_STATUS_CODES:
                raise ValidationError(f"Invalid status code '{command.status_code}'.")

            existing = asset_repo.get_by_number(company_id, command.asset_number)
            if existing is not None and existing.id != asset_id:
                raise ConflictError(f"Asset number '{command.asset_number}' already exists for this company.")

            cat_repo = self._asset_category_repository_factory(uow.session)
            cat = cat_repo.get_by_id(company_id, command.asset_category_id)
            if cat is None or cat.company_id != company_id:
                raise ValidationError(f"Asset category {command.asset_category_id} not found in this company.")

            if command.supplier_id is not None:
                self._validate_supplier(uow.session, company_id, command.supplier_id)

            asset.asset_number = command.asset_number.strip()
            asset.asset_name = command.asset_name.strip()
            asset.asset_category_id = command.asset_category_id
            asset.acquisition_date = command.acquisition_date
            asset.capitalization_date = command.capitalization_date
            asset.acquisition_cost = command.acquisition_cost
            asset.salvage_value = command.salvage_value
            asset.useful_life_months = command.useful_life_months
            asset.depreciation_method_code = command.depreciation_method_code
            asset.status_code = command.status_code
            asset.supplier_id = command.supplier_id
            asset.purchase_bill_id = command.purchase_bill_id
            asset.notes = command.notes
            asset_repo.save(asset)
            uow.commit()
            asset = asset_repo.get_by_id(company_id, asset_id)
            from seeker_accounting.modules.audit.event_type_catalog import ASSET_UPDATED
            self._record_audit(company_id, ASSET_UPDATED, "Asset", asset.id, "Updated fixed asset")
            return self._to_detail_dto(asset)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _validate_asset_fields(
        self, asset_number: str, asset_name: str, acquisition_cost, salvage_value,
        useful_life_months: int, method_code: str
    ) -> None:
        from decimal import Decimal
        if not asset_number or not asset_number.strip():
            raise ValidationError("Asset number is required.")
        if not asset_name or not asset_name.strip():
            raise ValidationError("Asset name is required.")
        if Decimal(str(acquisition_cost)) <= 0:
            raise ValidationError("Acquisition cost must be greater than zero.")
        if salvage_value is not None and Decimal(str(salvage_value)) < 0:
            raise ValidationError("Salvage value cannot be negative.")
        if salvage_value is not None and Decimal(str(salvage_value)) >= Decimal(str(acquisition_cost)):
            raise ValidationError("Salvage value must be less than acquisition cost.")
        if useful_life_months <= 0:
            raise ValidationError("Useful life must be greater than zero months.")
        if method_code not in VALID_DEPRECIATION_METHODS:
            raise ValidationError(
                f"Depreciation method '{method_code}' is not recognized. "
                f"Valid: {', '.join(sorted(VALID_DEPRECIATION_METHODS))}."
            )

    def _validate_supplier(self, session: Session, company_id: int, supplier_id: int) -> None:
        sup_repo = self._supplier_repository_factory(session)
        supplier = sup_repo.get_by_id(company_id, supplier_id)
        if supplier is None:
            raise ValidationError(f"Supplier {supplier_id} not found in this company.")

    def _require_company(self, session: Session, company_id: int) -> None:
        repo = self._company_repository_factory(session)
        if repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company {company_id} not found.")

    def _to_list_item_dto(self, asset: Asset) -> AssetListItemDTO:
        return AssetListItemDTO(
            id=asset.id,
            company_id=asset.company_id,
            asset_number=asset.asset_number,
            asset_name=asset.asset_name,
            asset_category_id=asset.asset_category_id,
            asset_category_code=asset.category.code if asset.category else "",
            asset_category_name=asset.category.name if asset.category else "",
            acquisition_date=asset.acquisition_date,
            capitalization_date=asset.capitalization_date,
            acquisition_cost=asset.acquisition_cost,
            salvage_value=asset.salvage_value,
            useful_life_months=asset.useful_life_months,
            depreciation_method_code=asset.depreciation_method_code,
            status_code=asset.status_code,
            supplier_id=asset.supplier_id,
            supplier_name=asset.supplier.supplier_name if asset.supplier else None,
        )

    def _to_detail_dto(self, asset: Asset) -> AssetDetailDTO:
        return AssetDetailDTO(
            id=asset.id,
            company_id=asset.company_id,
            asset_number=asset.asset_number,
            asset_name=asset.asset_name,
            asset_category_id=asset.asset_category_id,
            asset_category_code=asset.category.code if asset.category else "",
            asset_category_name=asset.category.name if asset.category else "",
            acquisition_date=asset.acquisition_date,
            capitalization_date=asset.capitalization_date,
            acquisition_cost=asset.acquisition_cost,
            salvage_value=asset.salvage_value,
            useful_life_months=asset.useful_life_months,
            depreciation_method_code=asset.depreciation_method_code,
            status_code=asset.status_code,
            supplier_id=asset.supplier_id,
            supplier_name=asset.supplier.supplier_name if asset.supplier else None,
            purchase_bill_id=asset.purchase_bill_id,
            notes=asset.notes,
            asset_account_id=asset.category.asset_account_id if asset.category else 0,
            asset_account_code=asset.category.asset_account.account_code if (asset.category and asset.category.asset_account) else "",
            accumulated_depreciation_account_id=asset.category.accumulated_depreciation_account_id if asset.category else 0,
            depreciation_expense_account_id=asset.category.depreciation_expense_account_id if asset.category else 0,
            created_at=asset.created_at,
            updated_at=asset.updated_at,
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
        from seeker_accounting.modules.audit.event_type_catalog import MODULE_FIXED_ASSETS
        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type_code,
                    module_code=MODULE_FIXED_ASSETS,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    description=description,
                ),
            )
        except Exception:
            pass  # Audit must not break business operations
