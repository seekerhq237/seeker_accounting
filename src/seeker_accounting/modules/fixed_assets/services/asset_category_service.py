from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.accounting.chart_of_accounts.repositories.account_repository import (
    AccountRepository,
)
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.fixed_assets.dto.asset_category_commands import (
    CreateAssetCategoryCommand,
    UpdateAssetCategoryCommand,
)
from seeker_accounting.modules.fixed_assets.dto.asset_category_dto import (
    AssetCategoryDetailDTO,
    AssetCategoryListItemDTO,
)
from seeker_accounting.modules.fixed_assets.models.asset_category import AssetCategory
from seeker_accounting.modules.fixed_assets.repositories.asset_category_repository import (
    AssetCategoryRepository,
)
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

AssetCategoryRepositoryFactory = Callable[[Session], AssetCategoryRepository]
AccountRepositoryFactory = Callable[[Session], AccountRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]


class AssetCategoryService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        asset_category_repository_factory: AssetCategoryRepositoryFactory,
        account_repository_factory: AccountRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._asset_category_repository_factory = asset_category_repository_factory
        self._account_repository_factory = account_repository_factory
        self._company_repository_factory = company_repository_factory
        self._audit_service = audit_service

    def list_asset_categories(
        self, company_id: int, active_only: bool = False
    ) -> list[AssetCategoryListItemDTO]:
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._asset_category_repository_factory(uow.session)
            rows = repo.list_by_company(company_id, active_only=active_only)
            return [self._to_list_item_dto(r) for r in rows]

    def get_asset_category(self, company_id: int, category_id: int) -> AssetCategoryDetailDTO:
        with self._unit_of_work_factory() as uow:
            repo = self._asset_category_repository_factory(uow.session)
            cat = repo.get_by_id(company_id, category_id)
            if cat is None or cat.company_id != company_id:
                raise NotFoundError(f"Asset category {category_id} not found.")
            return self._to_detail_dto(cat)

    def create_asset_category(
        self, company_id: int, command: CreateAssetCategoryCommand
    ) -> AssetCategoryDetailDTO:
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            self._validate_command_fields(command.code, command.name, command.default_useful_life_months,
                                          command.default_depreciation_method_code)
            repo = self._asset_category_repository_factory(uow.session)
            if repo.get_by_code(company_id, command.code) is not None:
                raise ConflictError(f"Asset category code '{command.code}' already exists for this company.")
            self._validate_accounts(uow.session, company_id,
                                    command.asset_account_id,
                                    command.accumulated_depreciation_account_id,
                                    command.depreciation_expense_account_id)
            cat = AssetCategory(
                company_id=company_id,
                code=command.code.strip().upper(),
                name=command.name.strip(),
                asset_account_id=command.asset_account_id,
                accumulated_depreciation_account_id=command.accumulated_depreciation_account_id,
                depreciation_expense_account_id=command.depreciation_expense_account_id,
                default_useful_life_months=command.default_useful_life_months,
                default_depreciation_method_code=command.default_depreciation_method_code,
                is_active=True,
            )
            repo.save(cat)
            uow.commit()
            from seeker_accounting.modules.audit.event_type_catalog import ASSET_CATEGORY_CREATED
            self._record_audit(company_id, ASSET_CATEGORY_CREATED, "AssetCategory", cat.id, "Created asset category")
            return self._to_detail_dto(cat)

    def update_asset_category(
        self, company_id: int, category_id: int, command: UpdateAssetCategoryCommand
    ) -> AssetCategoryDetailDTO:
        with self._unit_of_work_factory() as uow:
            repo = self._asset_category_repository_factory(uow.session)
            cat = repo.get_by_id(company_id, category_id)
            if cat is None or cat.company_id != company_id:
                raise NotFoundError(f"Asset category {category_id} not found.")
            self._validate_command_fields(command.code, command.name, command.default_useful_life_months,
                                          command.default_depreciation_method_code)
            # Check code uniqueness if changed
            existing = repo.get_by_code(company_id, command.code)
            if existing is not None and existing.id != category_id:
                raise ConflictError(f"Asset category code '{command.code}' already exists for this company.")
            self._validate_accounts(uow.session, company_id,
                                    command.asset_account_id,
                                    command.accumulated_depreciation_account_id,
                                    command.depreciation_expense_account_id)
            cat.code = command.code.strip().upper()
            cat.name = command.name.strip()
            cat.asset_account_id = command.asset_account_id
            cat.accumulated_depreciation_account_id = command.accumulated_depreciation_account_id
            cat.depreciation_expense_account_id = command.depreciation_expense_account_id
            cat.default_useful_life_months = command.default_useful_life_months
            cat.default_depreciation_method_code = command.default_depreciation_method_code
            cat.is_active = command.is_active
            repo.save(cat)
            uow.commit()
            from seeker_accounting.modules.audit.event_type_catalog import ASSET_CATEGORY_UPDATED
            self._record_audit(company_id, ASSET_CATEGORY_UPDATED, "AssetCategory", cat.id, "Updated asset category")
            return self._to_detail_dto(cat)

    def deactivate_asset_category(self, company_id: int, category_id: int) -> None:
        with self._unit_of_work_factory() as uow:
            repo = self._asset_category_repository_factory(uow.session)
            cat = repo.get_by_id(company_id, category_id)
            if cat is None or cat.company_id != company_id:
                raise NotFoundError(f"Asset category {category_id} not found.")
            cat.is_active = False
            repo.save(cat)
            uow.commit()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_command_fields(
        self, code: str, name: str, default_useful_life_months: int, method_code: str
    ) -> None:
        if not code or not code.strip():
            raise ValidationError("Asset category code is required.")
        if not name or not name.strip():
            raise ValidationError("Asset category name is required.")
        if default_useful_life_months <= 0:
            raise ValidationError("Default useful life must be greater than zero months.")
        if method_code not in VALID_DEPRECIATION_METHODS:
            raise ValidationError(
                f"Depreciation method '{method_code}' is not a recognized built-in method. "
                f"Valid methods: {', '.join(sorted(VALID_DEPRECIATION_METHODS))}."
            )

    def _validate_accounts(
        self,
        session: Session,
        company_id: int,
        asset_account_id: int,
        accumulated_depreciation_account_id: int,
        depreciation_expense_account_id: int,
    ) -> None:
        account_repo = self._account_repository_factory(session)
        for account_id, label in [
            (asset_account_id, "Asset account"),
            (accumulated_depreciation_account_id, "Accumulated depreciation account"),
            (depreciation_expense_account_id, "Depreciation expense account"),
        ]:
            acct = account_repo.get_by_id(company_id, account_id)
            if acct is None:
                raise ValidationError(f"{label} (id={account_id}) was not found.")
            if acct.company_id != company_id:
                raise ValidationError(f"{label} does not belong to this company.")
            if not acct.is_active:
                raise ValidationError(f"{label} '{acct.account_code}' is inactive.")

    def _require_company(self, session: Session, company_id: int) -> None:
        repo = self._company_repository_factory(session)
        if repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company {company_id} not found.")

    def _to_list_item_dto(self, cat: AssetCategory) -> AssetCategoryListItemDTO:
        return AssetCategoryListItemDTO(
            id=cat.id,
            company_id=cat.company_id,
            code=cat.code,
            name=cat.name,
            asset_account_id=cat.asset_account_id,
            asset_account_code=cat.asset_account.account_code if cat.asset_account else "",
            asset_account_name=cat.asset_account.account_name if cat.asset_account else "",
            accumulated_depreciation_account_id=cat.accumulated_depreciation_account_id,
            accumulated_depreciation_account_code=(
                cat.accumulated_depreciation_account.account_code
                if cat.accumulated_depreciation_account else ""
            ),
            accumulated_depreciation_account_name=(
                cat.accumulated_depreciation_account.account_name
                if cat.accumulated_depreciation_account else ""
            ),
            depreciation_expense_account_id=cat.depreciation_expense_account_id,
            depreciation_expense_account_code=(
                cat.depreciation_expense_account.account_code
                if cat.depreciation_expense_account else ""
            ),
            depreciation_expense_account_name=(
                cat.depreciation_expense_account.account_name
                if cat.depreciation_expense_account else ""
            ),
            default_useful_life_months=cat.default_useful_life_months,
            default_depreciation_method_code=cat.default_depreciation_method_code,
            is_active=cat.is_active,
        )

    def _to_detail_dto(self, cat: AssetCategory) -> AssetCategoryDetailDTO:
        return AssetCategoryDetailDTO(
            id=cat.id,
            company_id=cat.company_id,
            code=cat.code,
            name=cat.name,
            asset_account_id=cat.asset_account_id,
            asset_account_code=cat.asset_account.account_code if cat.asset_account else "",
            asset_account_name=cat.asset_account.account_name if cat.asset_account else "",
            accumulated_depreciation_account_id=cat.accumulated_depreciation_account_id,
            accumulated_depreciation_account_code=(
                cat.accumulated_depreciation_account.account_code
                if cat.accumulated_depreciation_account else ""
            ),
            accumulated_depreciation_account_name=(
                cat.accumulated_depreciation_account.account_name
                if cat.accumulated_depreciation_account else ""
            ),
            depreciation_expense_account_id=cat.depreciation_expense_account_id,
            depreciation_expense_account_code=(
                cat.depreciation_expense_account.account_code
                if cat.depreciation_expense_account else ""
            ),
            depreciation_expense_account_name=(
                cat.depreciation_expense_account.account_name
                if cat.depreciation_expense_account else ""
            ),
            default_useful_life_months=cat.default_useful_life_months,
            default_depreciation_method_code=cat.default_depreciation_method_code,
            is_active=cat.is_active,
            created_at=cat.created_at,
            updated_at=cat.updated_at,
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
