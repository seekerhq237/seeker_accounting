from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.inventory.dto.traceability_dto import (
    CreateItemBatchCommand,
    CreateItemSerialCommand,
    ItemBatchDTO,
    ItemSerialDTO,
    UpdateItemBatchCommand,
    UpdateItemSerialCommand,
)
from seeker_accounting.modules.inventory.models.item_batch import BATCH_STATUS_CODES, ItemBatch
from seeker_accounting.modules.inventory.models.item_serial import SERIAL_STATUS_CODES, ItemSerial
from seeker_accounting.modules.inventory.repositories.item_batch_repository import ItemBatchRepository
from seeker_accounting.modules.inventory.repositories.item_repository import ItemRepository
from seeker_accounting.modules.inventory.repositories.item_serial_repository import ItemSerialRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService


CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
ItemRepositoryFactory = Callable[[Session], ItemRepository]
ItemBatchRepositoryFactory = Callable[[Session], ItemBatchRepository]
ItemSerialRepositoryFactory = Callable[[Session], ItemSerialRepository]


class ItemTraceabilityService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        item_repository_factory: ItemRepositoryFactory,
        item_batch_repository_factory: ItemBatchRepositoryFactory,
        item_serial_repository_factory: ItemSerialRepositoryFactory,
        permission_service: PermissionService | None = None,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory
        self._item_repository_factory = item_repository_factory
        self._item_batch_repository_factory = item_batch_repository_factory
        self._item_serial_repository_factory = item_serial_repository_factory
        self._permission_service = permission_service
        self._audit_service = audit_service

    def list_batches(self, company_id: int, item_id: int | None = None) -> list[ItemBatchDTO]:
        self._require_permission("inventory.traceability.manage")
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._item_batch_repository_factory(uow.session)
            return [self._batch_to_dto(batch) for batch in repo.list_by_item(company_id, item_id)]

    def create_batch(self, company_id: int, command: CreateItemBatchCommand) -> ItemBatchDTO:
        self._require_permission("inventory.traceability.manage")
        batch_number = self._normalize_code(command.batch_number, "Batch number")
        self._validate_date_range(command.manufactured_on, command.expiry_on)
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            item = self._require_item(uow.session, company_id, command.item_id)
            if item.tracking_mode_code not in {"batch", "serial"}:
                raise ValidationError("Only batch- or serial-tracked items can have batches.")
            batch_repo = self._item_batch_repository_factory(uow.session)
            if batch_repo.get_by_number(company_id, command.item_id, batch_number) is not None:
                raise ConflictError("A batch with this number already exists for the item.")
            batch = ItemBatch(
                company_id=company_id,
                item_id=command.item_id,
                batch_number=batch_number,
                manufactured_on=command.manufactured_on,
                expiry_on=command.expiry_on,
                supplier_id=command.supplier_id,
                status_code="active",
                notes=self._normalize_optional_text(command.notes),
            )
            batch_repo.add(batch)
            self._commit_or_translate(uow)
            self._record_audit(company_id, "ITEM_BATCH_CREATED", "ItemBatch", batch.id, f"Batch {batch.batch_number} created for {item.item_code}.")
            return self._batch_to_dto(batch)

    def update_batch(self, company_id: int, command: UpdateItemBatchCommand) -> ItemBatchDTO:
        self._require_permission("inventory.traceability.manage")
        batch_number = self._normalize_code(command.batch_number, "Batch number")
        status_code = self._normalize_choice(command.status_code, BATCH_STATUS_CODES, "Batch status")
        self._validate_date_range(command.manufactured_on, command.expiry_on)
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            batch_repo = self._item_batch_repository_factory(uow.session)
            batch = batch_repo.get_by_id(company_id, command.batch_id)
            if batch is None:
                raise NotFoundError(f"Batch with id {command.batch_id} was not found.")
            duplicate = batch_repo.get_by_number(company_id, batch.item_id, batch_number)
            if duplicate is not None and duplicate.id != batch.id:
                raise ConflictError("A batch with this number already exists for the item.")
            batch.batch_number = batch_number
            batch.status_code = status_code
            batch.manufactured_on = command.manufactured_on
            batch.expiry_on = command.expiry_on
            batch.supplier_id = command.supplier_id
            batch.notes = self._normalize_optional_text(command.notes)
            batch_repo.save(batch)
            self._commit_or_translate(uow)
            self._record_audit(company_id, "ITEM_BATCH_UPDATED", "ItemBatch", batch.id, f"Batch {batch.batch_number} updated.")
            return self._batch_to_dto(batch)

    def list_serials(self, company_id: int, item_id: int | None = None) -> list[ItemSerialDTO]:
        self._require_permission("inventory.traceability.manage")
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._item_serial_repository_factory(uow.session)
            return [self._serial_to_dto(serial) for serial in repo.list_by_item(company_id, item_id)]

    def create_serial(self, company_id: int, command: CreateItemSerialCommand) -> ItemSerialDTO:
        self._require_permission("inventory.traceability.manage")
        serial_number = self._normalize_code(command.serial_number, "Serial number")
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            item = self._require_item(uow.session, company_id, command.item_id)
            if item.tracking_mode_code != "serial":
                raise ValidationError("Only serial-tracked items can have serial records.")
            self._validate_batch_for_item(uow.session, company_id, command.item_id, command.batch_id)
            serial_repo = self._item_serial_repository_factory(uow.session)
            if serial_repo.get_by_number(company_id, command.item_id, serial_number) is not None:
                raise ConflictError("A serial number already exists for the item.")
            serial = ItemSerial(
                company_id=company_id,
                item_id=command.item_id,
                serial_number=serial_number,
                batch_id=command.batch_id,
                status_code="allocated",
                warranty_until=command.warranty_until,
                notes=self._normalize_optional_text(command.notes),
            )
            serial_repo.add(serial)
            self._commit_or_translate(uow)
            self._record_audit(company_id, "ITEM_SERIAL_CREATED", "ItemSerial", serial.id, f"Serial {serial.serial_number} created for {item.item_code}.")
            return self._serial_to_dto(serial)

    def update_serial(self, company_id: int, command: UpdateItemSerialCommand) -> ItemSerialDTO:
        self._require_permission("inventory.traceability.manage")
        serial_number = self._normalize_code(command.serial_number, "Serial number")
        status_code = self._normalize_choice(command.status_code, SERIAL_STATUS_CODES, "Serial status")
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            serial_repo = self._item_serial_repository_factory(uow.session)
            serial = serial_repo.get_by_id(company_id, command.serial_id)
            if serial is None:
                raise NotFoundError(f"Serial with id {command.serial_id} was not found.")
            self._validate_batch_for_item(uow.session, company_id, serial.item_id, command.batch_id)
            duplicate = serial_repo.get_by_number(company_id, serial.item_id, serial_number)
            if duplicate is not None and duplicate.id != serial.id:
                raise ConflictError("A serial number already exists for the item.")
            serial.serial_number = serial_number
            serial.status_code = status_code
            serial.batch_id = command.batch_id
            serial.current_location_id = command.current_location_id
            serial.warranty_until = command.warranty_until
            serial.notes = self._normalize_optional_text(command.notes)
            serial_repo.save(serial)
            self._commit_or_translate(uow)
            self._record_audit(company_id, "ITEM_SERIAL_UPDATED", "ItemSerial", serial.id, f"Serial {serial.serial_number} updated.")
            return self._serial_to_dto(serial)

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

    def _validate_batch_for_item(
        self,
        session: Session,
        company_id: int,
        item_id: int,
        batch_id: int | None,
    ) -> None:
        if batch_id is None:
            return
        batch = self._item_batch_repository_factory(session).get_by_id(company_id, batch_id)
        if batch is None or batch.item_id != item_id:
            raise ValidationError("Batch must belong to the same company and item as the serial.")

    def _commit_or_translate(self, uow) -> None:
        try:
            uow.commit()
        except IntegrityError as exc:
            raise ConflictError("Traceability record conflicts with an existing record.") from exc

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
    def _normalize_code(value: str, label: str) -> str:
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
    def _validate_date_range(manufactured_on, expiry_on) -> None:
        if manufactured_on is not None and expiry_on is not None and expiry_on < manufactured_on:
            raise ValidationError("Expiry date cannot be before manufacture date.")

    @staticmethod
    def _batch_to_dto(batch: ItemBatch) -> ItemBatchDTO:
        return ItemBatchDTO(
            id=batch.id,
            company_id=batch.company_id,
            item_id=batch.item_id,
            batch_number=batch.batch_number,
            status_code=batch.status_code,
            manufactured_on=batch.manufactured_on,
            expiry_on=batch.expiry_on,
            supplier_id=batch.supplier_id,
            notes=batch.notes,
        )

    @staticmethod
    def _serial_to_dto(serial: ItemSerial) -> ItemSerialDTO:
        return ItemSerialDTO(
            id=serial.id,
            company_id=serial.company_id,
            item_id=serial.item_id,
            serial_number=serial.serial_number,
            status_code=serial.status_code,
            batch_id=serial.batch_id,
            current_location_id=serial.current_location_id,
            current_doc_line_id=serial.current_doc_line_id,
            warranty_until=serial.warranty_until,
            notes=serial.notes,
        )