from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.inventory.dto.inventory_document_commands import (
    CreateInventoryDocumentCommand,
    InventoryDocumentLineCommand,
    SubmitInventoryDocumentCommand,
)
from seeker_accounting.modules.inventory.dto.production_order_dto import (
    BuildProductionDocumentsCommand,
    CompleteProductionOrderCommand,
    CreateProductionOrderCommand,
    ProductionOrderDTO,
)
from seeker_accounting.modules.inventory.repositories.item_repository import ItemRepository
from seeker_accounting.modules.inventory.models.production_order import ProductionOrder
from seeker_accounting.modules.inventory.repositories.bill_of_material_repository import BillOfMaterialRepository
from seeker_accounting.modules.inventory.repositories.inventory_document_repository import InventoryDocumentRepository
from seeker_accounting.modules.inventory.repositories.production_order_repository import ProductionOrderRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError
from seeker_accounting.platform.numbering.numbering_service import NumberingService

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService
    from seeker_accounting.modules.inventory.services.inventory_document_service import InventoryDocumentService
    from seeker_accounting.modules.inventory.services.inventory_posting_service import InventoryPostingService


CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
BillOfMaterialRepositoryFactory = Callable[[Session], BillOfMaterialRepository]
InventoryDocumentRepositoryFactory = Callable[[Session], InventoryDocumentRepository]
ItemRepositoryFactory = Callable[[Session], ItemRepository]
ProductionOrderRepositoryFactory = Callable[[Session], ProductionOrderRepository]


class ProductionOrderService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        bill_of_material_repository_factory: BillOfMaterialRepositoryFactory,
        inventory_document_repository_factory: InventoryDocumentRepositoryFactory,
        item_repository_factory: ItemRepositoryFactory,
        production_order_repository_factory: ProductionOrderRepositoryFactory,
        numbering_service: NumberingService | None = None,
        inventory_document_service: "InventoryDocumentService | None" = None,
        inventory_posting_service: "InventoryPostingService | None" = None,
        permission_service: PermissionService | None = None,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory
        self._bill_of_material_repository_factory = bill_of_material_repository_factory
        self._inventory_document_repository_factory = inventory_document_repository_factory
        self._item_repository_factory = item_repository_factory
        self._production_order_repository_factory = production_order_repository_factory
        self._numbering_service = numbering_service
        self._inventory_document_service = inventory_document_service
        self._inventory_posting_service = inventory_posting_service
        self._permission_service = permission_service
        self._audit_service = audit_service

    def list_orders(self, company_id: int) -> list[ProductionOrderDTO]:
        self._require_permission("inventory.production.manage")
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._production_order_repository_factory(uow.session)
            return [self._to_dto(order) for order in repo.list_by_company(company_id)]

    def create_order(self, company_id: int, command: CreateProductionOrderCommand) -> ProductionOrderDTO:
        self._require_permission("inventory.production.manage")
        if command.quantity_to_produce <= Decimal("0"):
            raise ValidationError("Quantity to produce must be greater than zero.")
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            bom = self._bill_of_material_repository_factory(uow.session).get_by_id(company_id, command.bom_id)
            if bom is None:
                raise NotFoundError(f"Bill of material with id {command.bom_id} was not found.")
            if bom.status_code != "active":
                raise ValidationError("Only active bills of material can be used for production orders.")
            order = ProductionOrder(
                company_id=company_id,
                order_number=self._issue_number(uow.session, company_id),
                bom_id=bom.id,
                finished_item_id=bom.item_id,
                location_id=command.location_id,
                order_date=command.order_date,
                quantity_to_produce=command.quantity_to_produce,
                status_code="draft",
                notes=self._normalize_optional_text(command.notes),
            )
            self._production_order_repository_factory(uow.session).add(order)
            self._commit_or_translate(uow)
            self._record_audit(company_id, "PRODUCTION_ORDER_CREATED", "ProductionOrder", order.id, f"Production order {order.order_number} created.")
            return self._to_dto(order)

    def build_documents(
        self,
        company_id: int,
        command: BuildProductionDocumentsCommand,
    ) -> ProductionOrderDTO:
        self._require_permission("inventory.production.manage")
        if self._inventory_document_service is None:
            raise ValidationError("Inventory document service is not configured for production automation.")
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            order = self._production_order_repository_factory(uow.session).get_by_id(
                company_id, command.production_order_id
            )
            if order is None:
                raise NotFoundError(f"Production order with id {command.production_order_id} was not found.")
            if order.status_code not in {"draft", "released", "in_progress"}:
                raise ValidationError("Only draft, released, or in-progress production orders can build production documents.")
            if order.finished_receipt_document_id is not None:
                if order.component_issue_document_id is None:
                    raise ValidationError("Production order has a finished receipt but no component issue document.")
                existing_receipt = self._inventory_document_repository_factory(uow.session).get_by_id(
                    company_id,
                    order.finished_receipt_document_id,
                )
                if existing_receipt is None:
                    raise ValidationError("Production order references a missing finished receipt document.")
                if command.post_immediately:
                    receipt_document_id = existing_receipt.id
                    issue_document_id = order.component_issue_document_id
                    receipt_status = existing_receipt.status_code
                    order_id = order.id
                    uow.commit()
                    if receipt_status != "posted":
                        self._post_document(company_id, receipt_document_id, command.actor_user_id)
                    return self.complete_order(
                        company_id,
                        CompleteProductionOrderCommand(
                            production_order_id=order_id,
                            component_issue_document_id=issue_document_id,
                            finished_receipt_document_id=receipt_document_id,
                            completed_by_user_id=command.actor_user_id,
                        ),
                    )
                return self._to_dto(order)
            if order.component_issue_document_id is not None:
                issue_doc = self._inventory_document_repository_factory(uow.session).get_by_id(
                    company_id,
                    order.component_issue_document_id,
                )
                if issue_doc is None:
                    raise ValidationError("Production order references a missing component issue document.")
                issue_document_id = issue_doc.id
                order_snapshot = self._to_dto(order)
                uow.commit()
                if command.post_immediately and issue_doc.status_code != "posted":
                    self._post_document(company_id, issue_document_id, command.actor_user_id)
                    self._mark_in_progress(company_id, order_snapshot.id)
                if command.post_immediately:
                    return self._build_and_post_receipt(company_id, order_snapshot.id, issue_document_id, command.actor_user_id)
                return self._reload_order_dto(company_id, order_snapshot.id)
            bom = self._bill_of_material_repository_factory(uow.session).get_by_id(company_id, order.bom_id)
            if bom is None or bom.status_code != "active":
                raise ValidationError("Production order must reference an active bill of material.")
            item_repo = self._item_repository_factory(uow.session)
            component_lines = []
            for component in bom.components:
                item = item_repo.get_by_id(company_id, component.component_item_id)
                if item is None:
                    raise ValidationError(f"BOM component item {component.component_item_id} was not found.")
                component_quantity = self._component_quantity(order.quantity_to_produce, component.quantity_per, component.scrap_percent)
                component_lines.append(
                    InventoryDocumentLineCommand(
                        item_id=component.component_item_id,
                        quantity=component_quantity,
                        unit_cost=None,
                        batch_id=self._component_batch_id(component.component_item_id, item.tracking_mode_code, command),
                        serial_ids=self._component_serial_ids(component.component_item_id, item.tracking_mode_code, command),
                    )
                )
            order_snapshot = self._to_dto(order)
            issue_command = CreateInventoryDocumentCommand(
                document_type_code="production_issue",
                document_date=order.order_date,
                location_id=order.location_id,
                reference_number=order.order_number,
                notes=f"Component issue for production order {order.order_number}",
                source_module_code="inventory",
                source_document_type="production_order",
                source_document_id=order.id,
                bom_id=order.bom_id,
                production_order_id=order.id,
                lines=tuple(component_lines),
            )
            uow.commit()

        issue_doc = self._inventory_document_service.create_draft_document(company_id, issue_command)
        self._assign_issue_document(company_id, order_snapshot.id, issue_doc.id, "released")
        if command.post_immediately:
            self._post_document(company_id, issue_doc.id, command.actor_user_id)
            self._mark_in_progress(company_id, order_snapshot.id)
            return self._build_and_post_receipt(company_id, order_snapshot.id, issue_doc.id, command.actor_user_id)
        return self._reload_order_dto(company_id, order_snapshot.id)

    def release_order(self, company_id: int, production_order_id: int) -> ProductionOrderDTO:
        self._require_permission("inventory.production.manage")
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._production_order_repository_factory(uow.session)
            order = repo.get_by_id(company_id, production_order_id)
            if order is None:
                raise NotFoundError(f"Production order with id {production_order_id} was not found.")
            if order.status_code != "draft":
                raise ValidationError("Only draft production orders can be released.")
            order.status_code = "released"
            repo.save(order)
            self._commit_or_translate(uow)
            return self._to_dto(order)

    def complete_order(self, company_id: int, command: CompleteProductionOrderCommand) -> ProductionOrderDTO:
        self._require_permission("inventory.production.manage")
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._production_order_repository_factory(uow.session)
            doc_repo = self._inventory_document_repository_factory(uow.session)
            order = repo.get_by_id(company_id, command.production_order_id)
            if order is None:
                raise NotFoundError(f"Production order with id {command.production_order_id} was not found.")
            if order.status_code not in {"draft", "released", "in_progress"}:
                raise ValidationError("Only draft, released, or in-progress production orders can be completed.")
            issue_doc = doc_repo.get_by_id(company_id, command.component_issue_document_id)
            receipt_doc = doc_repo.get_by_id(company_id, command.finished_receipt_document_id)
            if issue_doc is None or receipt_doc is None:
                raise ValidationError("Both component issue and finished receipt documents must exist.")
            if issue_doc.status_code != "posted" or receipt_doc.status_code != "posted":
                raise ValidationError("Production issue and receipt documents must be posted before completion.")
            order.component_issue_document_id = issue_doc.id
            order.finished_receipt_document_id = receipt_doc.id
            order.status_code = "completed"
            order.completed_at = datetime.utcnow()
            order.completed_by_user_id = command.completed_by_user_id
            repo.save(order)
            self._commit_or_translate(uow)
            return self._to_dto(order)

    def _build_and_post_receipt(
        self,
        company_id: int,
        production_order_id: int,
        issue_document_id: int,
        actor_user_id: int | None,
    ) -> ProductionOrderDTO:
        if self._inventory_document_service is None or self._inventory_posting_service is None:
            raise ValidationError("Production posting services are not configured.")
        with self._unit_of_work_factory() as uow:
            order = self._production_order_repository_factory(uow.session).get_by_id(company_id, production_order_id)
            if order is None:
                raise NotFoundError(f"Production order with id {production_order_id} was not found.")
            issue_doc = self._inventory_document_repository_factory(uow.session).get_detail(company_id, issue_document_id)
            if issue_doc is None or issue_doc.status_code != "posted":
                raise ValidationError("Component issue document must be posted before production receipt.")
            if order.finished_receipt_document_id is not None:
                receipt_doc = self._inventory_document_repository_factory(uow.session).get_by_id(
                    company_id,
                    order.finished_receipt_document_id,
                )
                if receipt_doc is None:
                    raise ValidationError("Production order references a missing finished receipt document.")
                receipt_document_id = receipt_doc.id
                receipt_status = receipt_doc.status_code
                uow.commit()
                if receipt_status != "posted":
                    self._post_document(company_id, receipt_document_id, actor_user_id)
                return self.complete_order(
                    company_id,
                    CompleteProductionOrderCommand(
                        production_order_id=production_order_id,
                        component_issue_document_id=issue_document_id,
                        finished_receipt_document_id=receipt_document_id,
                        completed_by_user_id=actor_user_id,
                    ),
                )
            bom = self._bill_of_material_repository_factory(uow.session).get_by_id(company_id, order.bom_id)
            if bom is None:
                raise ValidationError("Production order bill of material could not be loaded.")
            issue_value = sum((abs(line.line_amount or Decimal("0.00")) for line in issue_doc.lines), Decimal("0.00"))
            overhead = (bom.overhead_per_unit or Decimal("0.00")) * order.quantity_to_produce
            receipt_unit_cost = ((issue_value + overhead) / order.quantity_to_produce).quantize(Decimal("0.0001"))
            receipt_command = CreateInventoryDocumentCommand(
                document_type_code="production_receipt",
                document_date=order.order_date,
                location_id=order.location_id,
                reference_number=order.order_number,
                notes=f"Finished receipt for production order {order.order_number}",
                source_module_code="inventory",
                source_document_type="production_order",
                source_document_id=order.id,
                bom_id=order.bom_id,
                production_order_id=order.id,
                lines=(
                    InventoryDocumentLineCommand(
                        item_id=order.finished_item_id,
                        quantity=order.quantity_to_produce,
                        unit_cost=receipt_unit_cost,
                    ),
                ),
            )
            uow.commit()

        receipt_doc = self._inventory_document_service.create_draft_document(company_id, receipt_command)
        self._assign_receipt_document(company_id, production_order_id, receipt_doc.id)
        self._post_document(company_id, receipt_doc.id, actor_user_id)
        return self.complete_order(
            company_id,
            CompleteProductionOrderCommand(
                production_order_id=production_order_id,
                component_issue_document_id=issue_document_id,
                finished_receipt_document_id=receipt_doc.id,
                completed_by_user_id=actor_user_id,
            ),
        )

    def _post_document(self, company_id: int, document_id: int, actor_user_id: int | None) -> None:
        if self._inventory_document_service is None or self._inventory_posting_service is None:
            raise ValidationError("Production posting services are not configured.")
        try:
            self._inventory_posting_service.post_inventory_document(company_id, document_id, actor_user_id=actor_user_id)
        except ValidationError as exc:
            if "submitted" not in str(exc).lower():
                raise
            self._inventory_document_service.submit_for_posting(
                company_id,
                document_id,
                SubmitInventoryDocumentCommand(submitted_by_user_id=None),
            )
            self._inventory_posting_service.post_inventory_document(company_id, document_id, actor_user_id=actor_user_id)

    def _assign_issue_document(self, company_id: int, production_order_id: int, document_id: int, status_code: str) -> None:
        with self._unit_of_work_factory() as uow:
            repo = self._production_order_repository_factory(uow.session)
            order = repo.get_by_id(company_id, production_order_id)
            if order is None:
                raise NotFoundError(f"Production order with id {production_order_id} was not found.")
            order.component_issue_document_id = document_id
            order.status_code = status_code
            repo.save(order)
            self._commit_or_translate(uow)

    def _assign_receipt_document(self, company_id: int, production_order_id: int, document_id: int) -> None:
        with self._unit_of_work_factory() as uow:
            repo = self._production_order_repository_factory(uow.session)
            order = repo.get_by_id(company_id, production_order_id)
            if order is None:
                raise NotFoundError(f"Production order with id {production_order_id} was not found.")
            order.finished_receipt_document_id = document_id
            order.status_code = "in_progress"
            repo.save(order)
            self._commit_or_translate(uow)

    def _mark_in_progress(self, company_id: int, production_order_id: int) -> None:
        with self._unit_of_work_factory() as uow:
            repo = self._production_order_repository_factory(uow.session)
            order = repo.get_by_id(company_id, production_order_id)
            if order is None:
                raise NotFoundError(f"Production order with id {production_order_id} was not found.")
            if order.status_code != "completed":
                order.status_code = "in_progress"
                repo.save(order)
                self._commit_or_translate(uow)

    @staticmethod
    def _component_batch_id(
        component_item_id: int,
        tracking_mode_code: str,
        command: BuildProductionDocumentsCommand,
    ) -> int | None:
        if tracking_mode_code != "batch":
            return None
        batch_id = (command.component_batch_ids or {}).get(component_item_id)
        if batch_id is None:
            raise ValidationError(f"Batch-tracked component item {component_item_id} requires a batch selection.")
        return batch_id

    @staticmethod
    def _component_serial_ids(
        component_item_id: int,
        tracking_mode_code: str,
        command: BuildProductionDocumentsCommand,
    ) -> tuple[int, ...]:
        if tracking_mode_code != "serial":
            return ()
        serial_ids = tuple((command.component_serial_ids or {}).get(component_item_id) or ())
        if not serial_ids:
            raise ValidationError(f"Serial-tracked component item {component_item_id} requires serial selections.")
        return serial_ids

    def _reload_order_dto(self, company_id: int, production_order_id: int) -> ProductionOrderDTO:
        with self._unit_of_work_factory() as uow:
            order = self._production_order_repository_factory(uow.session).get_by_id(company_id, production_order_id)
            if order is None:
                raise NotFoundError(f"Production order with id {production_order_id} was not found.")
            return self._to_dto(order)

    @staticmethod
    def _component_quantity(order_quantity: Decimal, quantity_per: Decimal, scrap_percent: Decimal) -> Decimal:
        scrap_multiplier = Decimal("1") + (scrap_percent / Decimal("100"))
        return (order_quantity * quantity_per * scrap_multiplier).quantize(Decimal("0.0001"))

    def _require_permission(self, permission_code: str) -> None:
        if self._permission_service is not None:
            self._permission_service.require_permission(permission_code)

    def _require_company(self, session: Session, company_id: int) -> None:
        if self._company_repository_factory(session).get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

    def _issue_number(self, session: Session, company_id: int) -> str:
        if self._numbering_service is not None:
            try:
                return self._numbering_service.issue_next_number(
                    session,
                    company_id=company_id,
                    document_type_code="PRODUCTION_ORDER",
                )
            except Exception:
                pass
        return f"PROD-{uuid.uuid4().hex[:8].upper()}"

    def _commit_or_translate(self, uow) -> None:
        try:
            uow.commit()
        except IntegrityError as exc:
            raise ConflictError("Production order conflicts with an existing record.") from exc

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
    def _normalize_optional_text(value: str | None) -> str | None:
        text = (value or "").strip()
        return text or None

    @staticmethod
    def _to_dto(order: ProductionOrder) -> ProductionOrderDTO:
        return ProductionOrderDTO(
            id=order.id,
            company_id=order.company_id,
            order_number=order.order_number,
            bom_id=order.bom_id,
            finished_item_id=order.finished_item_id,
            location_id=order.location_id,
            order_date=order.order_date,
            quantity_to_produce=order.quantity_to_produce,
            status_code=order.status_code,
            component_issue_document_id=order.component_issue_document_id,
            finished_receipt_document_id=order.finished_receipt_document_id,
            completed_at=order.completed_at,
            completed_by_user_id=order.completed_by_user_id,
            notes=order.notes,
        )