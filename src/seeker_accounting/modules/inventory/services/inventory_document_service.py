from __future__ import annotations
import logging

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.db.base import utcnow
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.inventory.dto.inventory_document_commands import (
    CancelInventoryDocumentCommand,
    CreateInventoryDocumentCommand,
    InventoryDocumentLineCommand,
    SubmitInventoryDocumentCommand,
    UpdateInventoryDocumentCommand,
)
from seeker_accounting.modules.inventory.dto.inventory_document_dto import (
    InventoryDocumentDetailDTO,
    InventoryDocumentLineDTO,
    InventoryDocumentListItemDTO,
)
from seeker_accounting.modules.inventory.models.inventory_document import InventoryDocument
from seeker_accounting.modules.inventory.models.inventory_document_line import InventoryDocumentLine
from seeker_accounting.modules.inventory.models.inventory_document_line_serial import (
    InventoryDocumentLineSerial,
)
from seeker_accounting.modules.inventory.models.item_batch import ItemBatch
from seeker_accounting.modules.inventory.models.item_serial import ItemSerial
from seeker_accounting.modules.inventory.repositories.inventory_cost_layer_repository import (
    InventoryCostLayerRepository,
)
from seeker_accounting.modules.inventory.repositories.inventory_document_line_repository import (
    InventoryDocumentLineRepository,
)
from seeker_accounting.modules.inventory.repositories.inventory_document_repository import (
    InventoryDocumentRepository,
)
from seeker_accounting.modules.inventory.repositories.inventory_document_type_repository import (
    InventoryDocumentTypeRepository,
)
from seeker_accounting.modules.inventory.repositories.inventory_location_repository import InventoryLocationRepository
from seeker_accounting.modules.inventory.repositories.item_repository import ItemRepository
from seeker_accounting.modules.inventory.repositories.unit_of_measure_repository import UnitOfMeasureRepository
from seeker_accounting.modules.job_costing.services.project_dimension_validation_service import (
    ProjectDimensionValidationService,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
ItemRepositoryFactory = Callable[[Session], ItemRepository]
InventoryDocumentRepositoryFactory = Callable[[Session], InventoryDocumentRepository]
InventoryDocumentLineRepositoryFactory = Callable[[Session], InventoryDocumentLineRepository]
InventoryCostLayerRepositoryFactory = Callable[[Session], InventoryCostLayerRepository]
InventoryLocationRepositoryFactory = Callable[[Session], InventoryLocationRepository]
UnitOfMeasureRepositoryFactory = Callable[[Session], UnitOfMeasureRepository]
InventoryDocumentTypeRepositoryFactory = Callable[[Session], InventoryDocumentTypeRepository]

# Legacy short codes still accepted for backwards compatibility with code paths
# pre-Slice-1.4. Migration backfills documents to the new taxonomy; the
# document-type repository is the source of truth going forward.
_LEGACY_DOCUMENT_TYPES = {"receipt", "issue", "adjustment"}

# Mapping from new (Slice 1.4) document-type codes to the legacy action class
# the rest of the service / posting code keys off ("receipt" / "issue" /
# "adjustment"). Document types that direct stock OUT map to "issue"; types
# that direct stock IN map to "receipt"; everything else (including reversals,
# transfers, revaluations) maps to "adjustment" and uses the line quantity
# sign to drive the actual posting branch.
_DOC_TYPE_ACTION: dict[str, str] = {
    "goods_receipt_purchase": "receipt",
    "goods_receipt_other": "receipt",
    "transfer_in": "receipt",
    "customer_return": "receipt",
    "production_receipt": "receipt",
    "opening_balance": "receipt",
    "consignment_in": "receipt",
    "adjustment_increase": "receipt",
    "count_gain": "receipt",
    "goods_issue_sale": "issue",
    "goods_issue_consumption": "issue",
    "transfer_out": "issue",
    "supplier_return": "issue",
    "production_issue": "issue",
    "consignment_out": "issue",
    "adjustment_decrease": "issue",
    "scrap": "issue",
    "wastage": "issue",
    "count_loss": "issue",
    "transfer_in_transit": "adjustment",
    "revaluation": "adjustment",
}


class InventoryDocumentService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        item_repository_factory: ItemRepositoryFactory,
        inventory_document_repository_factory: InventoryDocumentRepositoryFactory,
        inventory_document_line_repository_factory: InventoryDocumentLineRepositoryFactory,
        inventory_cost_layer_repository_factory: InventoryCostLayerRepositoryFactory,
        inventory_location_repository_factory: InventoryLocationRepositoryFactory | None = None,
        unit_of_measure_repository_factory: UnitOfMeasureRepositoryFactory | None = None,
        inventory_document_type_repository_factory: InventoryDocumentTypeRepositoryFactory | None = None,
        numbering_service=None,
        project_dimension_validation_service: ProjectDimensionValidationService | None = None,
        permission_service: PermissionService | None = None,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory
        self._item_repository_factory = item_repository_factory
        self._inventory_document_repository_factory = inventory_document_repository_factory
        self._inventory_document_line_repository_factory = inventory_document_line_repository_factory
        self._inventory_cost_layer_repository_factory = inventory_cost_layer_repository_factory
        self._inventory_location_repository_factory = inventory_location_repository_factory
        self._unit_of_measure_repository_factory = unit_of_measure_repository_factory
        self._inventory_document_type_repository_factory = inventory_document_type_repository_factory
        self._numbering_service = numbering_service
        self._project_dimension_validation_service = project_dimension_validation_service
        self._permission_service = permission_service
        self._audit_service = audit_service

    def list_inventory_documents(
        self,
        company_id: int,
        status_code: str | None = None,
        document_type_code: str | None = None,
    ) -> list[InventoryDocumentListItemDTO]:
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._inventory_document_repository_factory(uow.session)
            rows = repo.list_by_company(company_id, status_code=status_code, document_type_code=document_type_code)
            return [self._to_list_item_dto(r) for r in rows]

    def get_inventory_document(self, company_id: int, document_id: int) -> InventoryDocumentDetailDTO:
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._inventory_document_repository_factory(uow.session)
            doc = repo.get_detail(company_id, document_id)
            if doc is None:
                raise NotFoundError(f"Inventory document with id {document_id} was not found.")
            return self._to_detail_dto(doc)

    def create_draft_document(
        self,
        company_id: int,
        command: CreateInventoryDocumentCommand,
    ) -> InventoryDocumentDetailDTO:
        normalized_command = self._normalize_create_command(command)
        self._validate_document_type(normalized_command.document_type_code)
        if not normalized_command.lines:
            raise ValidationError("At least one document line is required.")

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            doc_type_action = self._resolve_document_type_action(
                uow.session, company_id, normalized_command.document_type_code
            )

            if normalized_command.location_id is not None and self._inventory_location_repository_factory is not None:
                loc_repo = self._inventory_location_repository_factory(uow.session)
                loc = loc_repo.get_by_id(company_id, normalized_command.location_id)
                if loc is None or not loc.is_active:
                    raise ValidationError("Inventory location must exist and be active.")

            item_repo = self._item_repository_factory(uow.session)
            doc_repo = self._inventory_document_repository_factory(uow.session)
            cost_layer_repo = self._inventory_cost_layer_repository_factory(uow.session)

            if self._project_dimension_validation_service is not None:
                self._project_dimension_validation_service.validate_header_dimensions(
                    session=uow.session,
                    company_id=company_id,
                    contract_id=normalized_command.contract_id,
                    project_id=normalized_command.project_id,
                )
            orm_lines, _ = self._build_document_lines(
                session=uow.session,
                company_id=company_id,
                document_type_code=doc_type_action,
                header_contract_id=normalized_command.contract_id,
                header_project_id=normalized_command.project_id,
                header_location_id=normalized_command.location_id,
                lines=normalized_command.lines,
                item_repo=item_repo,
                cost_layer_repo=cost_layer_repo,
            )

            draft_number = self._issue_draft_number(uow.session, company_id)
            doc = InventoryDocument(
                company_id=company_id,
                document_number=draft_number,
                document_type_code=normalized_command.document_type_code,
                document_date=normalized_command.document_date,
                status_code="draft",
                location_id=normalized_command.location_id,
                reference_number=normalized_command.reference_number,
                notes=normalized_command.notes,
                contract_id=normalized_command.contract_id,
                project_id=normalized_command.project_id,
                reason_code_id=normalized_command.reason_code_id,
                source_module_code=normalized_command.source_module_code,
                source_document_type=normalized_command.source_document_type,
                source_document_id=normalized_command.source_document_id,
                stock_count_session_id=normalized_command.stock_count_session_id,
                bom_id=normalized_command.bom_id,
                production_order_id=normalized_command.production_order_id,
            )
            doc.lines = orm_lines
            doc_repo.add(doc)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_integrity_error(exc) from exc

            # Re-fetch with loaded lines
            doc = doc_repo.get_detail(company_id, doc.id)
            from seeker_accounting.modules.audit.event_type_catalog import INVENTORY_DOCUMENT_CREATED
            self._record_audit(company_id, INVENTORY_DOCUMENT_CREATED, "InventoryDocument", doc.id, "Created inventory document")
            return self._to_detail_dto(doc)

    def update_draft_document(
        self,
        company_id: int,
        document_id: int,
        command: UpdateInventoryDocumentCommand,
    ) -> InventoryDocumentDetailDTO:
        normalized_command = self._normalize_update_command(command)
        self._validate_document_type(normalized_command.document_type_code)
        if not normalized_command.lines:
            raise ValidationError("At least one document line is required.")

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)

            if normalized_command.location_id is not None and self._inventory_location_repository_factory is not None:
                loc_repo = self._inventory_location_repository_factory(uow.session)
                loc = loc_repo.get_by_id(company_id, normalized_command.location_id)
                if loc is None or not loc.is_active:
                    raise ValidationError("Inventory location must exist and be active.")

            doc_repo = self._inventory_document_repository_factory(uow.session)
            item_repo = self._item_repository_factory(uow.session)
            line_repo = self._inventory_document_line_repository_factory(uow.session)
            cost_layer_repo = self._inventory_cost_layer_repository_factory(uow.session)

            doc = doc_repo.get_detail(company_id, document_id)
            if doc is None:
                raise NotFoundError(f"Inventory document with id {document_id} was not found.")
            if doc.status_code != "draft":
                raise ValidationError("Only draft documents can be edited.")

            doc_type_action = self._resolve_document_type_action(
                uow.session, company_id, normalized_command.document_type_code
            )

            # Remove old lines
            line_repo.delete_for_document(doc.id)
            uow.session.flush()

            if self._project_dimension_validation_service is not None:
                self._project_dimension_validation_service.validate_header_dimensions(
                    session=uow.session,
                    company_id=company_id,
                    contract_id=normalized_command.contract_id,
                    project_id=normalized_command.project_id,
                )
            new_lines, _ = self._build_document_lines(
                session=uow.session,
                company_id=company_id,
                document_type_code=doc_type_action,
                header_contract_id=normalized_command.contract_id,
                header_project_id=normalized_command.project_id,
                header_location_id=normalized_command.location_id,
                lines=normalized_command.lines,
                item_repo=item_repo,
                cost_layer_repo=cost_layer_repo,
                document_id=doc.id,
            )

            doc.document_type_code = normalized_command.document_type_code
            doc.document_date = normalized_command.document_date
            doc.location_id = normalized_command.location_id
            doc.reference_number = normalized_command.reference_number
            doc.notes = normalized_command.notes
            doc.contract_id = normalized_command.contract_id
            doc.project_id = normalized_command.project_id
            doc.reason_code_id = normalized_command.reason_code_id
            doc.source_module_code = normalized_command.source_module_code
            doc.source_document_type = normalized_command.source_document_type
            doc.source_document_id = normalized_command.source_document_id
            doc.stock_count_session_id = normalized_command.stock_count_session_id
            doc.bom_id = normalized_command.bom_id
            doc.production_order_id = normalized_command.production_order_id
            doc.lines = new_lines
            doc_repo.save(doc)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_integrity_error(exc) from exc

            doc = doc_repo.get_detail(company_id, doc.id)
            from seeker_accounting.modules.audit.event_type_catalog import INVENTORY_DOCUMENT_UPDATED
            self._record_audit(company_id, INVENTORY_DOCUMENT_UPDATED, "InventoryDocument", doc.id, "Updated inventory document")
            return self._to_detail_dto(doc)

    def submit_for_posting(
        self,
        company_id: int,
        document_id: int,
        command: SubmitInventoryDocumentCommand | None = None,
    ) -> InventoryDocumentDetailDTO:
        self._require_permission("inventory.documents.submit_for_posting")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._inventory_document_repository_factory(uow.session)
            doc = repo.get_detail(company_id, document_id)
            if doc is None:
                raise NotFoundError(f"Inventory document with id {document_id} was not found.")
            if doc.status_code != "draft":
                raise ValidationError("Only draft documents can be submitted for posting.")
            doc.status_code = "pending_posting"
            doc.submitted_at = utcnow()
            doc.submitted_by_user_id = command.submitted_by_user_id if command else None
            repo.save(doc)
            uow.commit()

            doc = repo.get_detail(company_id, doc.id)
            from seeker_accounting.modules.audit.event_type_catalog import (
                INVENTORY_DOCUMENT_SUBMITTED_FOR_POSTING,
            )
            self._record_audit(
                company_id,
                INVENTORY_DOCUMENT_SUBMITTED_FOR_POSTING,
                "InventoryDocument",
                doc.id,
                "Submitted inventory document for posting",
            )
            return self._to_detail_dto(doc)

    def cancel_draft_document(
        self,
        company_id: int,
        document_id: int,
        command: CancelInventoryDocumentCommand | None = None,
    ) -> None:
        self._require_permission("inventory.documents.cancel")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._inventory_document_repository_factory(uow.session)
            doc = repo.get_by_id(company_id, document_id)
            if doc is None:
                raise NotFoundError(f"Inventory document with id {document_id} was not found.")
            if doc.status_code != "draft":
                raise ValidationError("Only draft documents can be cancelled.")
            if command is None or command.reason_code_id is None:
                raise ValidationError("A cancellation reason code is required.")
            doc.status_code = "cancelled"
            doc.cancellation_reason_code_id = command.reason_code_id
            doc.cancelled_by_user_id = command.cancelled_by_user_id
            doc.cancelled_at = utcnow()
            repo.save(doc)
            uow.commit()

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _require_permission(self, permission_code: str) -> None:
        if self._permission_service is not None:
            self._permission_service.require_permission(permission_code)

    def _normalize_create_command(self, command: CreateInventoryDocumentCommand) -> CreateInventoryDocumentCommand:
        return CreateInventoryDocumentCommand(
            document_type_code=command.document_type_code,
            document_date=command.document_date,
            location_id=command.location_id,
            reference_number=command.reference_number,
            notes=command.notes,
            contract_id=self._normalize_optional_id(command.contract_id),
            project_id=self._normalize_optional_id(command.project_id),
            reason_code_id=self._normalize_optional_id(command.reason_code_id),
            source_module_code=command.source_module_code,
            source_document_type=command.source_document_type,
            source_document_id=self._normalize_optional_id(command.source_document_id),
            stock_count_session_id=self._normalize_optional_id(command.stock_count_session_id),
            bom_id=self._normalize_optional_id(command.bom_id),
            production_order_id=self._normalize_optional_id(command.production_order_id),
            lines=self._normalize_line_commands(command.lines),
        )

    def _normalize_update_command(self, command: UpdateInventoryDocumentCommand) -> UpdateInventoryDocumentCommand:
        return UpdateInventoryDocumentCommand(
            document_type_code=command.document_type_code,
            document_date=command.document_date,
            location_id=command.location_id,
            reference_number=command.reference_number,
            notes=command.notes,
            contract_id=self._normalize_optional_id(command.contract_id),
            project_id=self._normalize_optional_id(command.project_id),
            reason_code_id=self._normalize_optional_id(command.reason_code_id),
            source_module_code=command.source_module_code,
            source_document_type=command.source_document_type,
            source_document_id=self._normalize_optional_id(command.source_document_id),
            stock_count_session_id=self._normalize_optional_id(command.stock_count_session_id),
            bom_id=self._normalize_optional_id(command.bom_id),
            production_order_id=self._normalize_optional_id(command.production_order_id),
            lines=self._normalize_line_commands(command.lines),
        )

    def _normalize_line_commands(
        self,
        lines: tuple[InventoryDocumentLineCommand, ...],
    ) -> tuple[InventoryDocumentLineCommand, ...]:
        normalized_lines: list[InventoryDocumentLineCommand] = []
        for line in lines:
            normalized_lines.append(
                InventoryDocumentLineCommand(
                    item_id=line.item_id,
                    quantity=line.quantity,
                    unit_cost=line.unit_cost,
                    batch_id=self._normalize_optional_id(line.batch_id),
                    serial_ids=tuple(self._normalize_optional_id(serial_id) for serial_id in line.serial_ids),
                    counterparty_account_id=line.counterparty_account_id,
                    line_description=line.line_description,
                    transaction_uom_id=self._normalize_optional_id(line.transaction_uom_id),
                    contract_id=self._normalize_optional_id(line.contract_id),
                    project_id=self._normalize_optional_id(line.project_id),
                    project_job_id=self._normalize_optional_id(line.project_job_id),
                    project_cost_code_id=self._normalize_optional_id(line.project_cost_code_id),
                )
            )
        return tuple(normalized_lines)

    def _build_document_lines(
        self,
        *,
        session: Session,
        company_id: int,
        document_type_code: str,
        header_contract_id: int | None,
        header_project_id: int | None,
        header_location_id: int | None,
        lines: tuple[InventoryDocumentLineCommand, ...],
        item_repo: ItemRepository,
        cost_layer_repo: InventoryCostLayerRepository,
        document_id: int | None = None,
    ) -> tuple[list[InventoryDocumentLine], Decimal]:
        total_value = Decimal("0.00")
        built_lines: list[InventoryDocumentLine] = []
        for idx, line_cmd in enumerate(lines, start=1):
            item = item_repo.get_by_id(company_id, line_cmd.item_id)
            if item is None or not item.is_active:
                raise ValidationError(f"Line {idx}: Item must exist and be active.")
            if item.item_type_code != "stock":
                raise ValidationError(f"Line {idx}: Only stock items are allowed on inventory documents.")
            self._validate_traceability(
                session=session,
                company_id=company_id,
                line_number=idx,
                item=item,
                line_command=line_cmd,
                document_type_code=document_type_code,
            )

            self._validate_line_quantity(document_type_code, line_cmd.quantity, idx)
            self._validate_line_cost(document_type_code, line_cmd.unit_cost, idx)

            # -- UoM conversion (before stock check, since stock is in base UoM) --
            transaction_uom_id = line_cmd.transaction_uom_id
            uom_ratio_snapshot = None
            base_quantity = line_cmd.quantity  # default: no conversion

            if transaction_uom_id is not None and self._unit_of_measure_repository_factory is not None:
                uom_repo = self._unit_of_measure_repository_factory(session)
                txn_uom = uom_repo.get_by_id(company_id, transaction_uom_id)
                if txn_uom is None or not txn_uom.is_active:
                    raise ValidationError(f"Line {idx}: Transaction UoM must exist and be active.")

                item_uom = None
                if item.unit_of_measure_id is not None:
                    item_uom = uom_repo.get_by_id(company_id, item.unit_of_measure_id)

                if item_uom is not None and txn_uom.id != item_uom.id:
                    if txn_uom.category_id is None or item_uom.category_id is None:
                        raise ValidationError(
                            f"Line {idx}: Both transaction and item UoMs must belong to a category for conversion."
                        )
                    if txn_uom.category_id != item_uom.category_id:
                        raise ValidationError(
                            f"Line {idx}: Transaction UoM and item UoM must be in the same category."
                        )
                    if item_uom.ratio_to_base == 0:
                        raise ValidationError(f"Line {idx}: Item base UoM has invalid ratio.")
                    uom_ratio_snapshot = txn_uom.ratio_to_base
                    base_quantity = (
                        line_cmd.quantity * txn_uom.ratio_to_base / item_uom.ratio_to_base
                    ).quantize(Decimal("0.0001"))
                else:
                    uom_ratio_snapshot = txn_uom.ratio_to_base

            if document_type_code == "issue" or (
                document_type_code == "adjustment" and line_cmd.quantity < 0
            ):
                on_hand = cost_layer_repo.get_stock_on_hand(
                    company_id,
                    line_cmd.item_id,
                    location_id=header_location_id,
                    location_aware=True,
                    batch_id=line_cmd.batch_id,
                    batch_aware=line_cmd.batch_id is not None,
                )
                needed = abs(base_quantity)
                if needed > on_hand:
                    raise ValidationError(
                        f"Line {idx}: Insufficient stock for item '{item.item_code}'. "
                        f"On hand: {on_hand}, requested: {needed}."
                    )

            resolved_contract_id = None
            resolved_project_id = None
            resolved_project_job_id = None
            resolved_project_cost_code_id = None
            if self._project_dimension_validation_service is not None:
                resolved_dimensions = self._project_dimension_validation_service.resolve_line_dimensions(
                    header_contract_id=header_contract_id,
                    header_project_id=header_project_id,
                    line_contract_id=line_cmd.contract_id,
                    line_project_id=line_cmd.project_id,
                    line_project_job_id=line_cmd.project_job_id,
                    line_project_cost_code_id=line_cmd.project_cost_code_id,
                )
                self._project_dimension_validation_service.validate_line_dimensions(
                    session=session,
                    company_id=company_id,
                    contract_id=resolved_dimensions.contract_id,
                    project_id=resolved_dimensions.project_id,
                    project_job_id=resolved_dimensions.project_job_id,
                    project_cost_code_id=resolved_dimensions.project_cost_code_id,
                    line_number=idx,
                )
                resolved_contract_id = resolved_dimensions.contract_id
                resolved_project_id = resolved_dimensions.project_id
                resolved_project_job_id = resolved_dimensions.project_job_id
                resolved_project_cost_code_id = resolved_dimensions.project_cost_code_id

            line_amount = self._compute_line_amount(document_type_code, line_cmd.quantity, line_cmd.unit_cost)
            total_value += abs(line_amount) if line_amount else Decimal("0.00")

            orm_line = InventoryDocumentLine(
                inventory_document_id=document_id or 0,
                line_number=idx,
                item_id=line_cmd.item_id,
                batch_id=line_cmd.batch_id,
                quantity=line_cmd.quantity,
                unit_cost=line_cmd.unit_cost,
                line_amount=line_amount,
                counterparty_account_id=line_cmd.counterparty_account_id,
                line_description=line_cmd.line_description,
                transaction_uom_id=transaction_uom_id,
                uom_ratio_snapshot=uom_ratio_snapshot,
                base_quantity=base_quantity,
                contract_id=resolved_contract_id,
                project_id=resolved_project_id,
                project_job_id=resolved_project_job_id,
                project_cost_code_id=resolved_project_cost_code_id,
            )
            orm_line.serial_links = [
                InventoryDocumentLineSerial(serial_id=serial_id)
                for serial_id in line_cmd.serial_ids
            ]
            built_lines.append(orm_line)
        return built_lines, total_value

    def _validate_traceability(
        self,
        *,
        session: Session,
        company_id: int,
        line_number: int,
        item,
        line_command: InventoryDocumentLineCommand,
        document_type_code: str,
    ) -> None:
        tracking_mode = getattr(item, "tracking_mode_code", "none") or "none"
        if line_command.batch_id is not None:
            batch = session.get(ItemBatch, line_command.batch_id)
            if batch is None or batch.company_id != company_id or batch.item_id != item.id:
                raise ValidationError(f"Line {line_number}: Batch must belong to the selected item.")
        if tracking_mode == "batch" and line_command.batch_id is None:
            raise ValidationError(f"Line {line_number}: Batch is required for batch-tracked items.")

        if tracking_mode == "serial":
            quantity = abs(line_command.quantity)
            if quantity != quantity.to_integral_value():
                raise ValidationError(f"Line {line_number}: Serialized item quantity must be a whole number.")
            expected_count = int(quantity)
            if len(line_command.serial_ids) != expected_count:
                raise ValidationError(
                    f"Line {line_number}: {expected_count} serial number(s) must be selected."
                )
        elif line_command.serial_ids:
            raise ValidationError(f"Line {line_number}: Serial numbers are only allowed for serial-tracked items.")

        if not line_command.serial_ids:
            return

        serials = list(
            session.scalars(
                select(ItemSerial).where(
                    ItemSerial.company_id == company_id,
                    ItemSerial.item_id == item.id,
                    ItemSerial.id.in_(line_command.serial_ids),
                )
            )
        )
        if len(serials) != len(set(line_command.serial_ids)):
            raise ValidationError(f"Line {line_number}: One or more serial numbers are invalid.")
        acceptable_status = "allocated" if document_type_code == "receipt" else "in_stock"
        for serial in serials:
            if serial.status_code != acceptable_status:
                raise ValidationError(
                    f"Line {line_number}: Serial '{serial.serial_number}' is not {acceptable_status}."
                )

    def _issue_draft_number(self, session: Session, company_id: int) -> str:
        """Issue a draft document number using NumberingService when available.

        Falls back to a UUID-suffixed slug when no numbering service has been
        wired (e.g. tests that build the service directly).
        """
        if self._numbering_service is not None:
            try:
                return self._numbering_service.issue_next_number(
                    session,
                    company_id=company_id,
                    document_type_code="INVENTORY_DOCUMENT_DRAFT",
                )
            except Exception:
                pass
        return f"INV-DRAFT-{uuid.uuid4().hex[:8].upper()}"

    def _normalize_optional_id(self, value: int | None) -> int | None:
        if value is None:
            return None
        if value <= 0:
            raise ValidationError("Dimension identifiers must be greater than zero.")
        return value

    def _resolve_document_type_action(
        self, session: Session, company_id: int, doc_type_code: str
    ) -> str:
        """Resolve a document type code to a legacy action ('receipt'|'issue'|'adjustment').

        Validates that the code exists in the company's document-type catalog
        when a document-type repository factory is configured.
        """
        if doc_type_code in _LEGACY_DOCUMENT_TYPES:
            return doc_type_code
        if self._inventory_document_type_repository_factory is not None:
            repo = self._inventory_document_type_repository_factory(session)
            row = repo.get_by_code(company_id, doc_type_code)
            if row is None or not row.is_active:
                raise ValidationError(
                    f"Document type '{doc_type_code}' is not configured for this company."
                )
        action = _DOC_TYPE_ACTION.get(doc_type_code)
        if action is None:
            raise ValidationError(
                f"Document type '{doc_type_code}' is not supported."
            )
        return action

    def _validate_document_type(self, doc_type: str) -> None:
        # Backwards-compat shim: legacy short codes always pass; new codes
        # are validated through ``_resolve_document_type_action`` against
        # the document-type catalog.
        if doc_type in _LEGACY_DOCUMENT_TYPES:
            return
        if doc_type in _DOC_TYPE_ACTION:
            return
        raise ValidationError(
            f"Document type '{doc_type}' is not supported."
        )

    def _validate_line_quantity(self, doc_type: str, quantity: Decimal, line_idx: int) -> None:
        if doc_type == "receipt":
            if quantity <= 0:
                raise ValidationError(f"Line {line_idx}: Receipt quantity must be positive.")
        elif doc_type == "issue":
            if quantity <= 0:
                raise ValidationError(f"Line {line_idx}: Issue quantity must be positive.")
        elif doc_type == "adjustment":
            if quantity == 0:
                raise ValidationError(f"Line {line_idx}: Adjustment quantity must not be zero.")

    def _validate_line_cost(self, doc_type: str, unit_cost: Decimal | None, line_idx: int) -> None:
        if doc_type == "receipt":
            if unit_cost is None or unit_cost <= 0:
                raise ValidationError(f"Line {line_idx}: Unit cost is required and must be positive for receipts.")
        elif doc_type == "adjustment":
            # Positive adjustments require unit_cost
            pass  # Validated at posting time with full context

    def _compute_line_amount(
        self, doc_type: str, quantity: Decimal, unit_cost: Decimal | None
    ) -> Decimal | None:
        if unit_cost is not None:
            return (quantity * unit_cost).quantize(Decimal("0.01"))
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _require_company_exists(self, session: Session | None, company_id: int) -> None:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        repo = self._company_repository_factory(session)
        if repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

    def _translate_integrity_error(self, exc: IntegrityError) -> ValidationError | ConflictError:
        msg = str(exc.orig).lower() if exc.orig is not None else str(exc).lower()
        if "unique" in msg and "document_number" in msg:
            return ConflictError("An inventory document with this number already exists.")
        return ValidationError("Inventory document could not be saved.")

    def _to_list_item_dto(self, doc: InventoryDocument) -> InventoryDocumentListItemDTO:
        return InventoryDocumentListItemDTO(
            id=doc.id,
            company_id=doc.company_id,
            document_number=doc.document_number,
            document_type_code=doc.document_type_code,
            document_date=doc.document_date,
            status_code=doc.status_code,
            reference_number=doc.reference_number,
            total_value=doc.total_value,
            posted_at=doc.posted_at,
            updated_at=doc.updated_at,
            submitted_at=doc.submitted_at,
            submitted_by_user_id=doc.submitted_by_user_id,
            reversal_document_id=doc.reversal_document_id,
            reversal_of_document_id=doc.reversal_of_document_id,
        )

    def _to_detail_dto(self, doc: InventoryDocument) -> InventoryDocumentDetailDTO:
        line_dtos = tuple(
            InventoryDocumentLineDTO(
                id=line.id,
                line_number=line.line_number,
                item_id=line.item_id,
                item_code=line.item.item_code if line.item else "",
                item_name=line.item.item_name if line.item else "",
                batch_id=line.batch_id,
                batch_number=line.batch.batch_number if line.batch else None,
                serial_ids=tuple(link.serial_id for link in line.serial_links),
                serial_numbers=tuple(
                    link.serial.serial_number for link in line.serial_links if link.serial is not None
                ),
                quantity=line.quantity,
                unit_cost=line.unit_cost,
                line_amount=line.line_amount,
                counterparty_account_id=line.counterparty_account_id,
                counterparty_account_code=None,
                line_description=line.line_description,
                transaction_uom_id=line.transaction_uom_id,
                transaction_uom_code=(
                    line.transaction_uom.code if line.transaction_uom else None
                ),
                uom_ratio_snapshot=line.uom_ratio_snapshot,
                base_quantity=line.base_quantity,
                contract_id=line.contract_id,
                project_id=line.project_id,
                project_job_id=line.project_job_id,
                project_cost_code_id=line.project_cost_code_id,
            )
            for line in sorted(doc.lines, key=lambda l: l.line_number)
        )
        return InventoryDocumentDetailDTO(
            id=doc.id,
            company_id=doc.company_id,
            document_number=doc.document_number,
            document_type_code=doc.document_type_code,
            document_date=doc.document_date,
            status_code=doc.status_code,
            location_id=doc.location_id,
            reference_number=doc.reference_number,
            notes=doc.notes,
            total_value=doc.total_value,
            posted_journal_entry_id=doc.posted_journal_entry_id,
            posted_at=doc.posted_at,
            posted_by_user_id=doc.posted_by_user_id,
            submitted_at=doc.submitted_at,
            submitted_by_user_id=doc.submitted_by_user_id,
            approved_at=doc.approved_at,
            approved_by_user_id=doc.approved_by_user_id,
            cancellation_reason_code_id=doc.cancellation_reason_code_id,
            cancelled_at=doc.cancelled_at,
            cancelled_by_user_id=doc.cancelled_by_user_id,
            reversal_of_document_id=doc.reversal_of_document_id,
            reversal_document_id=doc.reversal_document_id,
            reverse_reason_code_id=doc.reverse_reason_code_id,
            reversed_at=doc.reversed_at,
            reversed_by_user_id=doc.reversed_by_user_id,
            reversing_journal_entry_id=doc.reversing_journal_entry_id,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            contract_id=doc.contract_id,
            project_id=doc.project_id,
            reason_code_id=doc.reason_code_id,
            reason_code_code=(doc.reason_code.code if doc.reason_code is not None else None),
            source_module_code=doc.source_module_code,
            source_document_type=doc.source_document_type,
            source_document_id=doc.source_document_id,
            stock_count_session_id=doc.stock_count_session_id,
            bom_id=doc.bom_id,
            production_order_id=doc.production_order_id,
            lines=line_dtos,
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
            logging.getLogger(__name__).warning("Audit event failed", exc_info=True)
