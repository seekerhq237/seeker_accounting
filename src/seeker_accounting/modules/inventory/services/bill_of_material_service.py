from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.inventory.dto.bill_of_material_dto import (
    BillOfMaterialDTO,
    BomComponentCommand,
    BomComponentDTO,
    CreateBillOfMaterialCommand,
    UpdateBillOfMaterialCommand,
)
from seeker_accounting.modules.inventory.models.bill_of_material import (
    BOM_STATUS_CODES,
    BOM_TYPE_CODES,
    BillOfMaterial,
)
from seeker_accounting.modules.inventory.models.bom_component import BomComponent
from seeker_accounting.modules.inventory.repositories.bill_of_material_repository import (
    BillOfMaterialRepository,
)
from seeker_accounting.modules.inventory.repositories.item_repository import ItemRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService


CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
ItemRepositoryFactory = Callable[[Session], ItemRepository]
BillOfMaterialRepositoryFactory = Callable[[Session], BillOfMaterialRepository]


class BillOfMaterialService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        item_repository_factory: ItemRepositoryFactory,
        bill_of_material_repository_factory: BillOfMaterialRepositoryFactory,
        permission_service: PermissionService | None = None,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory
        self._item_repository_factory = item_repository_factory
        self._bill_of_material_repository_factory = bill_of_material_repository_factory
        self._permission_service = permission_service
        self._audit_service = audit_service

    def list_boms(self, company_id: int, item_id: int | None = None) -> list[BillOfMaterialDTO]:
        self._require_permission("inventory.boms.manage")
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._bill_of_material_repository_factory(uow.session)
            return [self._to_dto(bom) for bom in repo.list_by_company(company_id, item_id)]

    def get_bom(self, company_id: int, bom_id: int) -> BillOfMaterialDTO:
        self._require_permission("inventory.boms.manage")
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            bom = self._bill_of_material_repository_factory(uow.session).get_by_id(company_id, bom_id)
            if bom is None:
                raise NotFoundError(f"Bill of material with id {bom_id} was not found.")
            return self._to_dto(bom)

    def create_bom(self, company_id: int, command: CreateBillOfMaterialCommand) -> BillOfMaterialDTO:
        self._require_permission("inventory.boms.manage")
        version = self._normalize_required(command.version, "BOM version")
        type_code = self._normalize_choice(command.type_code, BOM_TYPE_CODES, "BOM type")
        self._validate_effective_dates(command.effective_from, command.effective_to)
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            self._require_item(uow.session, company_id, command.item_id)
            repo = self._bill_of_material_repository_factory(uow.session)
            if repo.get_by_version(company_id, command.item_id, version) is not None:
                raise ConflictError("A bill of material already exists for this item and version.")
            components = self._build_components(uow.session, company_id, command.item_id, command.components)
            bom = BillOfMaterial(
                company_id=company_id,
                item_id=command.item_id,
                version=version,
                type_code=type_code,
                status_code="draft",
                effective_from=command.effective_from,
                effective_to=command.effective_to,
                overhead_per_unit=command.overhead_per_unit,
                notes=self._normalize_optional_text(command.notes),
                components=components,
            )
            repo.add(bom)
            self._commit_or_translate(uow)
            self._record_audit(company_id, "BILL_OF_MATERIAL_CREATED", "BillOfMaterial", bom.id, f"BOM {bom.version} created.")
            return self._to_dto(bom)

    def update_bom(self, company_id: int, command: UpdateBillOfMaterialCommand) -> BillOfMaterialDTO:
        self._require_permission("inventory.boms.manage")
        version = self._normalize_required(command.version, "BOM version")
        type_code = self._normalize_choice(command.type_code, BOM_TYPE_CODES, "BOM type")
        status_code = self._normalize_choice(command.status_code, BOM_STATUS_CODES, "BOM status")
        self._validate_effective_dates(command.effective_from, command.effective_to)
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._bill_of_material_repository_factory(uow.session)
            bom = repo.get_by_id(company_id, command.bom_id)
            if bom is None:
                raise NotFoundError(f"Bill of material with id {command.bom_id} was not found.")
            duplicate = repo.get_by_version(company_id, bom.item_id, version)
            if duplicate is not None and duplicate.id != bom.id:
                raise ConflictError("A bill of material already exists for this item and version.")
            bom.version = version
            bom.type_code = type_code
            bom.status_code = status_code
            bom.effective_from = command.effective_from
            bom.effective_to = command.effective_to
            bom.overhead_per_unit = command.overhead_per_unit
            bom.notes = self._normalize_optional_text(command.notes)
            bom.components = self._build_components(uow.session, company_id, bom.item_id, command.components)
            repo.save(bom)
            self._commit_or_translate(uow)
            self._record_audit(company_id, "BILL_OF_MATERIAL_UPDATED", "BillOfMaterial", bom.id, f"BOM {bom.version} updated.")
            return self._to_dto(bom)

    def approve_bom(self, company_id: int, bom_id: int, actor_user_id: int | None = None) -> BillOfMaterialDTO:
        self._require_permission("inventory.boms.manage")
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            bom = self._bill_of_material_repository_factory(uow.session).get_by_id(company_id, bom_id)
            if bom is None:
                raise NotFoundError(f"Bill of material with id {bom_id} was not found.")
            if not bom.components:
                raise ValidationError("A bill of material must have at least one component before approval.")
            bom.status_code = "active"
            bom.approved_at = datetime.utcnow()
            bom.approved_by_user_id = actor_user_id
            self._commit_or_translate(uow)
            self._record_audit(company_id, "BILL_OF_MATERIAL_UPDATED", "BillOfMaterial", bom.id, f"BOM {bom.version} approved.")
            return self._to_dto(bom)

    def _build_components(
        self,
        session: Session,
        company_id: int,
        finished_item_id: int,
        commands: tuple[BomComponentCommand, ...],
    ) -> list[BomComponent]:
        if not commands:
            raise ValidationError("A bill of material must include at least one component.")
        seen_sequences: set[int] = set()
        seen_components: set[int] = set()
        components: list[BomComponent] = []
        for index, command in enumerate(commands, start=1):
            sequence = command.sequence if command.sequence is not None else index
            if sequence <= 0:
                raise ValidationError("BOM component sequence must be greater than zero.")
            if sequence in seen_sequences:
                raise ValidationError("BOM component sequences must be unique.")
            seen_sequences.add(sequence)
            if command.component_item_id == finished_item_id:
                raise ValidationError("A BOM component cannot be the same item as the finished item.")
            if command.component_item_id in seen_components:
                raise ValidationError("A component item can only appear once on a BOM.")
            seen_components.add(command.component_item_id)
            self._require_item(session, company_id, command.component_item_id)
            if command.quantity_per <= Decimal("0"):
                raise ValidationError("BOM component quantity must be greater than zero.")
            if command.scrap_percent < Decimal("0"):
                raise ValidationError("BOM component scrap percent cannot be negative.")
            components.append(
                BomComponent(
                    sequence=sequence,
                    component_item_id=command.component_item_id,
                    quantity_per=command.quantity_per,
                    scrap_percent=command.scrap_percent,
                    uom_id=command.uom_id,
                    notes=self._normalize_optional_text(command.notes),
                )
            )
        return components

    def _require_permission(self, permission_code: str) -> None:
        if self._permission_service is not None:
            self._permission_service.require_permission(permission_code)

    def _require_company(self, session: Session, company_id: int) -> None:
        if self._company_repository_factory(session).get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

    def _require_item(self, session: Session, company_id: int, item_id: int):
        item = self._item_repository_factory(session).get_by_id(company_id, item_id)
        if item is None:
            raise NotFoundError(f"Item with id {item_id} was not found.")
        return item

    @staticmethod
    def _normalize_required(value: str, label: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValidationError(f"{label} is required.")
        return text

    @staticmethod
    def _normalize_optional_text(value: str | None) -> str | None:
        text = (value or "").strip()
        return text or None

    @staticmethod
    def _normalize_choice(value: str, allowed: frozenset[str], label: str) -> str:
        normalized = (value or "").strip().lower()
        if normalized not in allowed:
            raise ValidationError(f"{label} must be one of: {', '.join(sorted(allowed))}.")
        return normalized

    @staticmethod
    def _validate_effective_dates(effective_from, effective_to) -> None:
        if effective_from is not None and effective_to is not None and effective_to < effective_from:
            raise ValidationError("Effective-to date cannot be before effective-from date.")

    def _commit_or_translate(self, uow) -> None:
        try:
            uow.commit()
        except IntegrityError as exc:
            raise ConflictError("Bill of material conflicts with an existing record.") from exc

    def _record_audit(self, company_id: int, event_type_code: str, entity_type: str, entity_id: int | None, description: str) -> None:
        if self._audit_service is None:
            return
        from seeker_accounting.modules.audit.dto.audit_event_dto import RecordAuditEventCommand
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
        except Exception:
            pass

    @staticmethod
    def _to_dto(bom: BillOfMaterial) -> BillOfMaterialDTO:
        return BillOfMaterialDTO(
            id=bom.id,
            company_id=bom.company_id,
            item_id=bom.item_id,
            version=bom.version,
            status_code=bom.status_code,
            type_code=bom.type_code,
            effective_from=bom.effective_from,
            effective_to=bom.effective_to,
            overhead_per_unit=bom.overhead_per_unit,
            notes=bom.notes,
            approved_at=bom.approved_at,
            approved_by_user_id=bom.approved_by_user_id,
            components=tuple(
                BomComponentDTO(
                    id=component.id,
                    bom_id=component.bom_id,
                    sequence=component.sequence,
                    component_item_id=component.component_item_id,
                    quantity_per=component.quantity_per,
                    scrap_percent=component.scrap_percent,
                    uom_id=component.uom_id,
                    notes=component.notes,
                )
                for component in sorted(bom.components, key=lambda row: row.sequence)
            ),
        )