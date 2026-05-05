"""Per-item GL account override service. Phase 0 / Slice 1.1."""

from __future__ import annotations

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
    CreateItemAccountOverrideCommand,
)
from seeker_accounting.modules.inventory.dto.item_dto import ItemAccountOverrideDTO
from seeker_accounting.modules.inventory.models.item_account_override import (
    ItemAccountOverride,
)
from seeker_accounting.modules.inventory.repositories.inventory_location_repository import (
    InventoryLocationRepository,
)
from seeker_accounting.modules.inventory.repositories.item_account_override_repository import (
    ItemAccountOverrideRepository,
)
from seeker_accounting.modules.inventory.repositories.item_repository import (
    ItemRepository,
)
from seeker_accounting.platform.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)

if TYPE_CHECKING:  # pragma: no cover
    from seeker_accounting.modules.audit.services.audit_service import AuditService


CompanyRepoFactory = Callable[[Session], CompanyRepository]
ItemRepoFactory = Callable[[Session], ItemRepository]
OverrideRepoFactory = Callable[[Session], ItemAccountOverrideRepository]
LocationRepoFactory = Callable[[Session], InventoryLocationRepository]


class ItemAccountOverrideService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepoFactory,
        item_repository_factory: ItemRepoFactory,
        override_repository_factory: OverrideRepoFactory,
        inventory_location_repository_factory: LocationRepoFactory,
        permission_service: PermissionService,
        audit_service: "AuditService | None" = None,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._company_repo_factory = company_repository_factory
        self._item_repo_factory = item_repository_factory
        self._override_repo_factory = override_repository_factory
        self._location_repo_factory = inventory_location_repository_factory
        self._permission_service = permission_service
        self._audit_service = audit_service

    def list_for_item(
        self, company_id: int, item_id: int
    ) -> list[ItemAccountOverrideDTO]:
        with self._uow_factory() as uow:
            self._require_item(uow.session, company_id, item_id)
            repo = self._override_repo_factory(uow.session)
            location_repo = self._location_repo_factory(uow.session)
            return [
                self._to_dto(r, location_repo, company_id)
                for r in repo.list_for_item(company_id, item_id)
            ]

    def create_override(
        self, company_id: int, command: CreateItemAccountOverrideCommand
    ) -> ItemAccountOverrideDTO:
        self._permission_service.require_permission(
            "inventory.account_overrides.manage"
        )
        self._validate_at_least_one_account(command)
        with self._uow_factory() as uow:
            self._require_item(uow.session, company_id, command.item_id)
            location_repo = self._location_repo_factory(uow.session)
            if command.location_id is not None:
                if location_repo.get_by_id(company_id, command.location_id) is None:
                    raise ValidationError("Inventory location was not found.")
            repo = self._override_repo_factory(uow.session)
            existing = repo.get_for_item_and_location(
                company_id, command.item_id, command.location_id
            )
            if existing is not None:
                raise ConflictError(
                    "An account override already exists for this item and location."
                )
            row = ItemAccountOverride(
                company_id=company_id,
                item_id=command.item_id,
                location_id=command.location_id,
                inventory_account_id=command.inventory_account_id,
                cogs_account_id=command.cogs_account_id,
                expense_account_id=command.expense_account_id,
                revenue_account_id=command.revenue_account_id,
            )
            repo.add(row)
            uow.commit()
            self._record_audit(
                company_id,
                "ITEM_ACCOUNT_OVERRIDE_CREATED",
                "ItemAccountOverride",
                row.id,
                f"Created GL account override for item {command.item_id}.",
            )
            self._record_override_applied(
                company_id,
                row.id,
                command,
            )
            return self._to_dto(row, location_repo, company_id)

    def delete_override(self, company_id: int, override_id: int) -> None:
        self._permission_service.require_permission(
            "inventory.account_overrides.manage"
        )
        with self._uow_factory() as uow:
            repo = self._override_repo_factory(uow.session)
            row = repo.get_by_id(company_id, override_id)
            if row is None:
                raise NotFoundError(
                    f"Item account override with id {override_id} was not found."
                )
            repo.delete(row)
            uow.commit()
            self._record_audit(
                company_id,
                "ITEM_ACCOUNT_OVERRIDE_DELETED",
                "ItemAccountOverride",
                override_id,
                f"Deleted GL account override {override_id}.",
            )

    # ------------------------------------------------------------------

    def _require_item(self, session: Session, company_id: int, item_id: int) -> None:
        company_repo = self._company_repo_factory(session)
        if company_repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")
        item_repo = self._item_repo_factory(session)
        if item_repo.get_by_id(company_id, item_id) is None:
            raise NotFoundError(f"Item with id {item_id} was not found.")

    def _validate_at_least_one_account(
        self, command: CreateItemAccountOverrideCommand
    ) -> None:
        if (
            command.inventory_account_id is None
            and command.cogs_account_id is None
            and command.expense_account_id is None
            and command.revenue_account_id is None
        ):
            raise ValidationError(
                "An account override must override at least one account."
            )

    def _to_dto(
        self,
        row: ItemAccountOverride,
        location_repo: InventoryLocationRepository,
        company_id: int,
    ) -> ItemAccountOverrideDTO:
        location_code: str | None = None
        if row.location_id is not None:
            loc = location_repo.get_by_id(company_id, row.location_id)
            location_code = loc.code if loc is not None else None
        return ItemAccountOverrideDTO(
            id=row.id,
            item_id=row.item_id,
            location_id=row.location_id,
            location_code=location_code,
            inventory_account_id=row.inventory_account_id,
            cogs_account_id=row.cogs_account_id,
            expense_account_id=row.expense_account_id,
            revenue_account_id=row.revenue_account_id,
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

    def _record_override_applied(
        self,
        company_id: int,
        override_id: int | None,
        command: CreateItemAccountOverrideCommand,
    ) -> None:
        if self._audit_service is None:
            return
        from seeker_accounting.modules.audit.event_type_catalog import MODULE_INVENTORY

        try:
            self._audit_service.record_override_applied(
                company_id,
                module_code=MODULE_INVENTORY,
                entity_type="ItemAccountOverride",
                entity_id=override_id,
                override_code="ITEM_ACCOUNT_MAPPING",
                reason="Inventory GL account mapping override configured.",
                description=f"Applied GL account override for item {command.item_id}.",
                context={
                    "item_id": command.item_id,
                    "location_id": command.location_id or 0,
                    "inventory_account": command.inventory_account_id is not None,
                    "cogs_account": command.cogs_account_id is not None,
                    "expense_account": command.expense_account_id is not None,
                    "revenue_account": command.revenue_account_id is not None,
                },
            )
        except Exception:  # pragma: no cover
            pass
