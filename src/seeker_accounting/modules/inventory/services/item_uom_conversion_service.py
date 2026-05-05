"""Per-item UoM conversion service.

Owns the matrix of unit-of-measure conversions for a single item, plus the
``convert_to_base_quantity`` helper used by inventory document services
when normalising line quantities. Phase 0 / Slice 1.3.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import (
    PermissionService,
)
from seeker_accounting.modules.companies.repositories.company_repository import (
    CompanyRepository,
)
from seeker_accounting.modules.inventory.dto.item_commands import (
    CreateItemUomConversionCommand,
    UpdateItemUomConversionCommand,
)
from seeker_accounting.modules.inventory.dto.item_dto import ItemUomConversionDTO
from seeker_accounting.modules.inventory.models.item_uom_conversion import (
    ItemUomConversion,
)
from seeker_accounting.modules.inventory.repositories.item_repository import (
    ItemRepository,
)
from seeker_accounting.modules.inventory.repositories.item_uom_conversion_repository import (
    ItemUomConversionRepository,
)
from seeker_accounting.modules.inventory.repositories.unit_of_measure_repository import (
    UnitOfMeasureRepository,
)
from seeker_accounting.platform.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from seeker_accounting.platform.numerics import quantize_quantity

if TYPE_CHECKING:  # pragma: no cover
    from seeker_accounting.modules.audit.services.audit_service import AuditService


CompanyRepoFactory = Callable[[Session], CompanyRepository]
ItemRepoFactory = Callable[[Session], ItemRepository]
ConversionRepoFactory = Callable[[Session], ItemUomConversionRepository]
UomRepoFactory = Callable[[Session], UnitOfMeasureRepository]


_ALLOWED_ROUNDING_RULES = {"none", "round_half_even", "round_up", "round_down"}


class ItemUomConversionService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepoFactory,
        item_repository_factory: ItemRepoFactory,
        conversion_repository_factory: ConversionRepoFactory,
        unit_of_measure_repository_factory: UomRepoFactory,
        permission_service: PermissionService,
        audit_service: "AuditService | None" = None,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._company_repo_factory = company_repository_factory
        self._item_repo_factory = item_repository_factory
        self._conv_repo_factory = conversion_repository_factory
        self._uom_repo_factory = unit_of_measure_repository_factory
        self._permission_service = permission_service
        self._audit_service = audit_service

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def list_for_item(
        self, company_id: int, item_id: int, active_only: bool = False
    ) -> list[ItemUomConversionDTO]:
        with self._uow_factory() as uow:
            self._require_item(uow.session, company_id, item_id)
            repo = self._conv_repo_factory(uow.session)
            uom_repo = self._uom_repo_factory(uow.session)
            rows = repo.list_for_item(company_id, item_id, active_only=active_only)
            return [self._to_dto(r, uom_repo, company_id) for r in rows]

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def create_conversion(
        self, company_id: int, command: CreateItemUomConversionCommand
    ) -> ItemUomConversionDTO:
        self._permission_service.require_permission("inventory.uom_conversions.manage")
        self._validate_command_fields(command.ratio_to_base, command.rounding_rule_code)
        with self._uow_factory() as uow:
            self._require_item(uow.session, company_id, command.item_id)
            uom_repo = self._uom_repo_factory(uow.session)
            uom = uom_repo.get_by_id(company_id, command.unit_of_measure_id)
            if uom is None or not uom.is_active:
                raise ValidationError("Unit of measure must exist and be active.")
            repo = self._conv_repo_factory(uow.session)
            if repo.get_by_item_and_uom(
                company_id, command.item_id, command.unit_of_measure_id
            ) is not None:
                raise ConflictError(
                    "A conversion already exists for this item and unit of measure."
                )
            self._enforce_single_default(
                repo, company_id, command.item_id,
                purchase_default=command.is_purchase_default,
                sales_default=command.is_sales_default,
            )
            row = ItemUomConversion(
                company_id=company_id,
                item_id=command.item_id,
                unit_of_measure_id=command.unit_of_measure_id,
                ratio_to_base=command.ratio_to_base,
                rounding_rule_code=command.rounding_rule_code,
                min_increment=command.min_increment,
                is_purchase_default=command.is_purchase_default,
                is_sales_default=command.is_sales_default,
                is_stocking=command.is_stocking,
                is_active=True,
            )
            repo.add(row)
            uow.commit()
            self._record_audit(
                company_id,
                "ITEM_UOM_CONVERSION_CREATED",
                "ItemUomConversion",
                row.id,
                f"Created UoM conversion for item {command.item_id}.",
            )
            return self._to_dto(row, uom_repo, company_id)

    def update_conversion(
        self,
        company_id: int,
        command: UpdateItemUomConversionCommand,
    ) -> ItemUomConversionDTO:
        self._permission_service.require_permission("inventory.uom_conversions.manage")
        self._validate_command_fields(command.ratio_to_base, command.rounding_rule_code)
        with self._uow_factory() as uow:
            repo = self._conv_repo_factory(uow.session)
            row = repo.get_by_id(company_id, command.conversion_id)
            if row is None:
                raise NotFoundError(
                    f"UoM conversion with id {command.conversion_id} was not found."
                )
            self._enforce_single_default(
                repo, company_id, row.item_id,
                purchase_default=command.is_purchase_default,
                sales_default=command.is_sales_default,
                exclude_id=row.id,
            )
            row.ratio_to_base = command.ratio_to_base
            row.rounding_rule_code = command.rounding_rule_code
            row.min_increment = command.min_increment
            row.is_purchase_default = command.is_purchase_default
            row.is_sales_default = command.is_sales_default
            row.is_stocking = command.is_stocking
            row.is_active = command.is_active
            repo.save(row)
            uow.commit()
            uom_repo = self._uom_repo_factory(uow.session)
            self._record_audit(
                company_id,
                "ITEM_UOM_CONVERSION_UPDATED",
                "ItemUomConversion",
                row.id,
                f"Updated UoM conversion {row.id}.",
            )
            return self._to_dto(row, uom_repo, company_id)

    # ------------------------------------------------------------------
    # Helpers usable from other services
    # ------------------------------------------------------------------

    def convert_to_base_quantity(
        self,
        session: Session,
        company_id: int,
        item_id: int,
        unit_of_measure_id: int,
        quantity: Decimal,
    ) -> tuple[Decimal, Decimal]:
        """Return ``(base_quantity, ratio_used)`` for a transaction quantity.

        When the requested UoM matches the item's base UoM (no conversion row
        exists, ratio implicitly = 1), returns the quantity untouched.
        """
        item_repo = self._item_repo_factory(session)
        item = item_repo.get_by_id(company_id, item_id)
        if item is None:
            raise NotFoundError(f"Item with id {item_id} was not found.")
        if unit_of_measure_id == item.unit_of_measure_id:
            return quantize_quantity(quantity), Decimal("1")
        conv_repo = self._conv_repo_factory(session)
        conversion = conv_repo.get_by_item_and_uom(
            company_id, item_id, unit_of_measure_id
        )
        if conversion is None or not conversion.is_active:
            raise ValidationError(
                "No active UoM conversion exists for this item and unit of measure."
            )
        ratio = conversion.ratio_to_base
        if ratio is None or ratio <= 0:
            raise ValidationError("UoM conversion ratio must be positive.")
        base_quantity = quantize_quantity(Decimal(quantity) * Decimal(ratio))
        return base_quantity, Decimal(ratio)

    # ------------------------------------------------------------------

    def _require_item(self, session: Session, company_id: int, item_id: int) -> None:
        company_repo = self._company_repo_factory(session)
        if company_repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")
        item_repo = self._item_repo_factory(session)
        if item_repo.get_by_id(company_id, item_id) is None:
            raise NotFoundError(f"Item with id {item_id} was not found.")

    def _validate_command_fields(self, ratio: Decimal, rounding_rule_code: str) -> None:
        if ratio is None or ratio <= 0:
            raise ValidationError("Conversion ratio must be a positive number.")
        if rounding_rule_code not in _ALLOWED_ROUNDING_RULES:
            raise ValidationError(
                "Rounding rule must be one of: "
                + ", ".join(sorted(_ALLOWED_ROUNDING_RULES))
            )

    def _enforce_single_default(
        self,
        repo: ItemUomConversionRepository,
        company_id: int,
        item_id: int,
        purchase_default: bool,
        sales_default: bool,
        exclude_id: int | None = None,
    ) -> None:
        if not purchase_default and not sales_default:
            return
        rows = repo.list_for_item(company_id, item_id)
        for row in rows:
            if exclude_id is not None and row.id == exclude_id:
                continue
            if purchase_default and row.is_purchase_default:
                row.is_purchase_default = False
                repo.save(row)
            if sales_default and row.is_sales_default:
                row.is_sales_default = False
                repo.save(row)

    def _to_dto(
        self,
        row: ItemUomConversion,
        uom_repo: UnitOfMeasureRepository,
        company_id: int,
    ) -> ItemUomConversionDTO:
        uom = uom_repo.get_by_id(company_id, row.unit_of_measure_id)
        return ItemUomConversionDTO(
            id=row.id,
            item_id=row.item_id,
            unit_of_measure_id=row.unit_of_measure_id,
            unit_of_measure_code=uom.code if uom is not None else "",
            ratio_to_base=row.ratio_to_base,
            rounding_rule_code=row.rounding_rule_code,
            min_increment=row.min_increment,
            is_purchase_default=row.is_purchase_default,
            is_sales_default=row.is_sales_default,
            is_stocking=row.is_stocking,
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
        from seeker_accounting.modules.audit.dto.audit_event_dto import (
            RecordAuditEventCommand,
        )
        from seeker_accounting.modules.audit.event_type_catalog import MODULE_INVENTORY

        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type_code,
                    module_code=MODULE_INVENTORY,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    description=description,
                ),
            )
        except Exception:  # pragma: no cover
            pass
