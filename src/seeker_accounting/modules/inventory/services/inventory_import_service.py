from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.inventory.dto.inventory_import_dto import (
    ApplyInventoryImportJobCommand,
    CreateInventoryImportJobCommand,
    InventoryImportJobDTO,
    InventoryImportJobRowDTO,
)
from seeker_accounting.modules.inventory.dto.inventory_document_commands import (
    CreateInventoryDocumentCommand,
    InventoryDocumentLineCommand,
    SubmitInventoryDocumentCommand,
)
from seeker_accounting.modules.inventory.dto.item_commands import CreateItemCommand
from seeker_accounting.modules.inventory.dto.traceability_dto import (
    CreateItemBatchCommand,
    CreateItemSerialCommand,
)
from seeker_accounting.modules.inventory.models.inventory_import_job import (
    InventoryImportJob,
    InventoryImportJobRow,
)
from seeker_accounting.modules.inventory.repositories.inventory_import_job_repository import (
    InventoryImportJobRepository,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService
    from seeker_accounting.modules.inventory.services.inventory_document_service import InventoryDocumentService
    from seeker_accounting.modules.inventory.services.inventory_posting_service import InventoryPostingService
    from seeker_accounting.modules.inventory.services.item_service import ItemService
    from seeker_accounting.modules.inventory.services.item_traceability_service import ItemTraceabilityService


CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
InventoryImportJobRepositoryFactory = Callable[[Session], InventoryImportJobRepository]


class InventoryImportService:
    _ALLOWED_ROW_STATUSES = {"valid", "invalid", "conflict"}

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        inventory_import_job_repository_factory: InventoryImportJobRepositoryFactory,
        item_service: "ItemService | None" = None,
        item_traceability_service: "ItemTraceabilityService | None" = None,
        inventory_document_service: "InventoryDocumentService | None" = None,
        inventory_posting_service: "InventoryPostingService | None" = None,
        permission_service: PermissionService | None = None,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory
        self._inventory_import_job_repository_factory = inventory_import_job_repository_factory
        self._item_service = item_service
        self._item_traceability_service = item_traceability_service
        self._inventory_document_service = inventory_document_service
        self._inventory_posting_service = inventory_posting_service
        self._permission_service = permission_service
        self._audit_service = audit_service

    def list_jobs(self, company_id: int) -> list[InventoryImportJobDTO]:
        self._require_permission("inventory.imports.manage")
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._inventory_import_job_repository_factory(uow.session)
            return [self._to_dto(job) for job in repo.list_by_company(company_id)]

    def create_preview_job(self, company_id: int, command: CreateInventoryImportJobCommand) -> InventoryImportJobDTO:
        self._require_permission("inventory.imports.manage")
        template_code = self._normalize_required(command.template_code, "Template code")
        rows = []
        valid_rows = 0
        invalid_rows = 0
        conflict_rows = 0
        for row_command in command.rows:
            if row_command.row_number <= 0:
                raise ValidationError("Import row number must be greater than zero.")
            status_code = self._normalize_row_status(row_command.status_code)
            if status_code == "valid":
                valid_rows += 1
            elif status_code == "invalid":
                invalid_rows += 1
            else:
                conflict_rows += 1
            rows.append(
                InventoryImportJobRow(
                    row_number=row_command.row_number,
                    status_code=status_code,
                    normalized_json=self._normalize_optional_text(row_command.normalized_json),
                    error_messages_json=self._normalize_optional_text(row_command.error_messages_json),
                )
            )
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            job = InventoryImportJob(
                company_id=company_id,
                template_code=template_code,
                source_filename=self._normalize_optional_text(command.source_filename),
                status_code="previewed",
                total_rows=len(rows),
                valid_rows=valid_rows,
                invalid_rows=invalid_rows,
                conflict_rows=conflict_rows,
                created_by_user_id=command.created_by_user_id,
                preview_json=self._normalize_optional_text(command.preview_json),
                error_summary=self._normalize_optional_text(command.error_summary),
                rows=rows,
            )
            self._inventory_import_job_repository_factory(uow.session).add(job)
            self._commit_or_translate(uow)
            self._record_audit(company_id, "INVENTORY_IMPORT_JOB_CREATED", "InventoryImportJob", job.id, f"Inventory import preview created for {template_code}.")
            return self._to_dto(job)

    def mark_applied(self, company_id: int, command: ApplyInventoryImportJobCommand) -> InventoryImportJobDTO:
        self._require_permission("inventory.imports.manage")
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._inventory_import_job_repository_factory(uow.session)
            job = repo.get_by_id(company_id, command.job_id)
            if job is None:
                raise NotFoundError(f"Inventory import job with id {command.job_id} was not found.")
            if job.status_code != "previewed":
                raise ValidationError("Only previewed inventory import jobs can be applied.")
            if job.invalid_rows or job.conflict_rows:
                raise ValidationError("Import job cannot be applied while invalid or conflict rows remain.")
            template_code = job.template_code
            row_payloads = tuple(
                (row.row_number, row.normalized_json)
                for row in sorted(job.rows, key=lambda value: value.row_number)
                if row.status_code == "valid"
            )
        self._apply_rows(company_id, template_code, row_payloads, command)
        with self._unit_of_work_factory() as uow:
            repo = self._inventory_import_job_repository_factory(uow.session)
            job = repo.get_by_id(company_id, command.job_id)
            if job is None:
                raise NotFoundError(f"Inventory import job with id {command.job_id} was not found.")
            if job.status_code != "previewed":
                raise ValidationError("Only previewed inventory import jobs can be applied.")
            job.status_code = "applied"
            job.applied_at = datetime.utcnow()
            job.applied_by_user_id = command.applied_by_user_id
            repo.save(job)
            self._commit_or_translate(uow)
            self._record_audit(company_id, "INVENTORY_IMPORT_JOB_APPLIED", "InventoryImportJob", job.id, f"Inventory import job {job.id} marked applied.")
            return self._to_dto(job)

    def _apply_rows(
        self,
        company_id: int,
        template_code: str,
        row_payloads: tuple[tuple[int, str | None], ...],
        command: ApplyInventoryImportJobCommand,
    ) -> None:
        normalized_template = self._normalize_template_code(template_code)
        payloads = [(row_number, self._decode_row(row_number, normalized_json)) for row_number, normalized_json in row_payloads]
        if not payloads:
            return
        if normalized_template in {"items", "item", "item_master", "item_masters"}:
            self._apply_item_rows(company_id, payloads)
            return
        if normalized_template in {"batches", "item_batches", "lots", "item_lots"}:
            self._apply_batch_rows(company_id, payloads)
            return
        if normalized_template in {"serials", "item_serials", "serial_numbers"}:
            self._apply_serial_rows(company_id, payloads)
            return
        if normalized_template in {"opening_balances", "opening_balance"}:
            self._apply_document_rows(company_id, payloads, "opening_balance", command)
            return
        if normalized_template in {"stock_adjustments", "inventory_adjustments", "adjustments"}:
            self._apply_document_rows(company_id, payloads, None, command)
            return
        if normalized_template in {"inventory_documents", "documents", "stock_documents"}:
            self._apply_document_rows(company_id, payloads, None, command)
            return
        raise ValidationError(f"Unsupported inventory import template '{template_code}'.")

    def _apply_item_rows(self, company_id: int, payloads: list[tuple[int, dict[str, Any]]]) -> None:
        if self._item_service is None:
            raise ValidationError("Item service is not configured for inventory import application.")
        for row_number, data in payloads:
            self._item_service.create_item(
                company_id,
                CreateItemCommand(
                    item_code=self._required_text(data, "item_code", row_number),
                    item_name=self._required_text(data, "item_name", row_number, aliases=("name",)),
                    item_type_code=self._optional_text(data, "item_type_code") or "inventory",
                    unit_of_measure_id=self._required_int(data, "unit_of_measure_id", row_number, aliases=("uom_id",)),
                    unit_of_measure_code=self._optional_text(data, "unit_of_measure_code", aliases=("uom_code",)) or "UNIT",
                    item_category_id=self._optional_int(data, "item_category_id", aliases=("category_id",)),
                    inventory_cost_method_code=self._optional_text(data, "inventory_cost_method_code", aliases=("costing_method_code", "cost_method_code")),
                    standard_cost=self._optional_decimal(data, "standard_cost"),
                    lifecycle_status_code=self._optional_text(data, "lifecycle_status_code", aliases=("status_code",)) or "active",
                    tracking_mode_code=self._optional_text(data, "tracking_mode_code", aliases=("tracking_mode",)) or "none",
                    parent_item_id=self._optional_int(data, "parent_item_id"),
                    is_variant=self._optional_bool(data, "is_variant", False),
                    attribute_values_json=self._optional_json_text(data, "attribute_values", aliases=("attribute_values_json",)),
                    is_sellable=self._optional_bool(data, "is_sellable", True),
                    is_purchasable=self._optional_bool(data, "is_purchasable", True),
                    is_stockable=self._optional_bool(data, "is_stockable", True),
                    ohada_stock_class_code=self._optional_text(data, "ohada_stock_class_code"),
                    inventory_account_id=self._optional_int(data, "inventory_account_id"),
                    cogs_account_id=self._optional_int(data, "cogs_account_id"),
                    expense_account_id=self._optional_int(data, "expense_account_id"),
                    revenue_account_id=self._optional_int(data, "revenue_account_id"),
                    purchase_tax_code_id=self._optional_int(data, "purchase_tax_code_id"),
                    sales_tax_code_id=self._optional_int(data, "sales_tax_code_id"),
                    reorder_level_quantity=self._optional_decimal(data, "reorder_level_quantity"),
                    description=self._optional_text(data, "description"),
                ),
            )

    def _apply_batch_rows(self, company_id: int, payloads: list[tuple[int, dict[str, Any]]]) -> None:
        if self._item_traceability_service is None:
            raise ValidationError("Traceability service is not configured for inventory import application.")
        for row_number, data in payloads:
            self._item_traceability_service.create_batch(
                company_id,
                CreateItemBatchCommand(
                    item_id=self._required_int(data, "item_id", row_number),
                    batch_number=self._required_text(data, "batch_number", row_number, aliases=("lot_number",)),
                    manufactured_on=self._optional_date(data, "manufactured_on", aliases=("manufacture_date",)),
                    expiry_on=self._optional_date(data, "expiry_on", aliases=("expiry_date",)),
                    supplier_id=self._optional_int(data, "supplier_id"),
                    notes=self._optional_text(data, "notes"),
                ),
            )

    def _apply_serial_rows(self, company_id: int, payloads: list[tuple[int, dict[str, Any]]]) -> None:
        if self._item_traceability_service is None:
            raise ValidationError("Traceability service is not configured for inventory import application.")
        for row_number, data in payloads:
            self._item_traceability_service.create_serial(
                company_id,
                CreateItemSerialCommand(
                    item_id=self._required_int(data, "item_id", row_number),
                    serial_number=self._required_text(data, "serial_number", row_number),
                    batch_id=self._optional_int(data, "batch_id"),
                    warranty_until=self._optional_date(data, "warranty_until", aliases=("warranty_expiry",)),
                    notes=self._optional_text(data, "notes"),
                ),
            )

    def _apply_document_rows(
        self,
        company_id: int,
        payloads: list[tuple[int, dict[str, Any]]],
        default_document_type_code: str | None,
        command: ApplyInventoryImportJobCommand,
    ) -> None:
        if self._inventory_document_service is None:
            raise ValidationError("Inventory document service is not configured for inventory import application.")
        document_commands: list[CreateInventoryDocumentCommand] = []
        grouped_lines: dict[tuple[str, date, int | None, int | None, str | None, str | None], list[InventoryDocumentLineCommand]] = defaultdict(list)
        for row_number, data in payloads:
            explicit_lines = data.get("lines")
            if isinstance(explicit_lines, list):
                document_commands.append(self._document_command_from_payload(row_number, data, default_document_type_code, command.job_id))
                continue
            document_type_code = self._document_type_for_row(data, default_document_type_code)
            document_date = self._required_date(data, "document_date", row_number, aliases=("date",))
            location_id = self._optional_int(data, "location_id")
            reason_code_id = self._optional_int(data, "reason_code_id")
            reference_number = self._optional_text(data, "reference_number", aliases=("reference",))
            notes = self._optional_text(data, "notes")
            grouped_lines[(document_type_code, document_date, location_id, reason_code_id, reference_number, notes)].append(
                self._line_command_from_payload(row_number, data, document_type_code)
            )
        for (document_type_code, document_date, location_id, reason_code_id, reference_number, notes), lines in grouped_lines.items():
            document_commands.append(
                CreateInventoryDocumentCommand(
                    document_type_code=document_type_code,
                    document_date=document_date,
                    location_id=location_id,
                    reference_number=reference_number,
                    notes=notes,
                    reason_code_id=reason_code_id,
                    source_module_code="inventory",
                    source_document_type="inventory_import_job",
                    source_document_id=command.job_id,
                    lines=tuple(lines),
                )
            )
        for document_command in document_commands:
            document = self._inventory_document_service.create_draft_document(company_id, document_command)
            if command.post_documents_immediately:
                self._post_import_document(company_id, document.id, command.applied_by_user_id)

    def _document_command_from_payload(
        self,
        row_number: int,
        data: dict[str, Any],
        default_document_type_code: str | None,
        job_id: int,
    ) -> CreateInventoryDocumentCommand:
        document_type_code = self._document_type_for_row(data, default_document_type_code)
        lines_payload = data.get("lines")
        if not isinstance(lines_payload, list) or not lines_payload:
            raise ValidationError(f"Import row {row_number} must contain at least one document line.")
        return CreateInventoryDocumentCommand(
            document_type_code=document_type_code,
            document_date=self._required_date(data, "document_date", row_number, aliases=("date",)),
            location_id=self._optional_int(data, "location_id"),
            reference_number=self._optional_text(data, "reference_number", aliases=("reference",)),
            notes=self._optional_text(data, "notes"),
            reason_code_id=self._optional_int(data, "reason_code_id"),
            source_module_code="inventory",
            source_document_type="inventory_import_job",
            source_document_id=job_id,
            lines=tuple(self._line_command_from_payload(row_number, line, document_type_code) for line in lines_payload),
        )

    def _post_import_document(self, company_id: int, document_id: int, actor_user_id: int | None) -> None:
        if self._inventory_posting_service is None:
            raise ValidationError("Inventory posting service is not configured for inventory import application.")
        try:
            self._inventory_posting_service.post_inventory_document(company_id, document_id, actor_user_id=actor_user_id)
        except ValidationError as exc:
            if "submitted" not in str(exc).lower() or self._inventory_document_service is None:
                raise
            self._inventory_document_service.submit_for_posting(
                company_id,
                document_id,
                SubmitInventoryDocumentCommand(submitted_by_user_id=None),
            )
            self._inventory_posting_service.post_inventory_document(company_id, document_id, actor_user_id=actor_user_id)

    def _line_command_from_payload(
        self,
        row_number: int,
        data: dict[str, Any],
        document_type_code: str,
    ) -> InventoryDocumentLineCommand:
        if not isinstance(data, dict):
            raise ValidationError(f"Import row {row_number} document lines must be JSON objects.")
        quantity = self._required_decimal(data, "quantity", row_number)
        if document_type_code in {"adjustment_increase", "opening_balance", "count_gain"}:
            quantity = abs(quantity)
        elif document_type_code in {"adjustment_decrease", "count_loss"}:
            quantity = abs(quantity)
        return InventoryDocumentLineCommand(
            item_id=self._required_int(data, "item_id", row_number),
            quantity=quantity,
            unit_cost=self._optional_decimal(data, "unit_cost"),
            batch_id=self._optional_int(data, "batch_id"),
            serial_ids=self._optional_int_tuple(data, "serial_ids", aliases=("serial_id",)),
            counterparty_account_id=self._optional_int(data, "counterparty_account_id"),
            line_description=self._optional_text(data, "line_description", aliases=("description",)),
            transaction_uom_id=self._optional_int(data, "transaction_uom_id", aliases=("uom_id",)),
            contract_id=self._optional_int(data, "contract_id"),
            project_id=self._optional_int(data, "project_id"),
            project_job_id=self._optional_int(data, "project_job_id"),
            project_cost_code_id=self._optional_int(data, "project_cost_code_id"),
        )

    def _document_type_for_row(self, data: dict[str, Any], default_document_type_code: str | None) -> str:
        document_type_code = self._optional_text(data, "document_type_code", aliases=("document_type",)) or default_document_type_code
        if document_type_code:
            return document_type_code
        quantity = self._optional_decimal(data, "quantity") or Decimal("0")
        return "adjustment_increase" if quantity >= 0 else "adjustment_decrease"

    def _decode_row(self, row_number: int, normalized_json: str | None) -> dict[str, Any]:
        if not normalized_json:
            raise ValidationError(f"Import row {row_number} has no normalized data.")
        try:
            payload = json.loads(normalized_json)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"Import row {row_number} normalized data is not valid JSON.") from exc
        if not isinstance(payload, dict):
            raise ValidationError(f"Import row {row_number} normalized data must be a JSON object.")
        return payload

    @staticmethod
    def _normalize_template_code(value: str) -> str:
        return (value or "").strip().lower().replace("-", "_").replace(" ", "_")

    def _required_text(self, data: dict[str, Any], key: str, row_number: int, aliases: tuple[str, ...] = ()) -> str:
        value = self._optional_text(data, key, aliases)
        if value is None:
            raise ValidationError(f"Import row {row_number} requires '{key}'.")
        return value

    def _required_int(self, data: dict[str, Any], key: str, row_number: int, aliases: tuple[str, ...] = ()) -> int:
        value = self._optional_int(data, key, aliases)
        if value is None:
            raise ValidationError(f"Import row {row_number} requires '{key}'.")
        return value

    def _required_decimal(self, data: dict[str, Any], key: str, row_number: int, aliases: tuple[str, ...] = ()) -> Decimal:
        value = self._optional_decimal(data, key, aliases)
        if value is None:
            raise ValidationError(f"Import row {row_number} requires '{key}'.")
        return value

    def _required_date(self, data: dict[str, Any], key: str, row_number: int, aliases: tuple[str, ...] = ()) -> date:
        value = self._optional_date(data, key, aliases)
        if value is None:
            raise ValidationError(f"Import row {row_number} requires '{key}'.")
        return value

    @staticmethod
    def _lookup(data: dict[str, Any], key: str, aliases: tuple[str, ...] = ()) -> Any:
        for candidate in (key, *aliases):
            if candidate in data:
                return data[candidate]
        return None

    def _optional_text(self, data: dict[str, Any], key: str, aliases: tuple[str, ...] = ()) -> str | None:
        value = self._lookup(data, key, aliases)
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _optional_json_text(self, data: dict[str, Any], key: str, aliases: tuple[str, ...] = ()) -> str | None:
        value = self._lookup(data, key, aliases)
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip()
            return text or None
        return json.dumps(value, sort_keys=True, separators=(",", ":"))

    def _optional_int(self, data: dict[str, Any], key: str, aliases: tuple[str, ...] = ()) -> int | None:
        value = self._lookup(data, key, aliases)
        if value is None or value == "":
            return None
        return int(value)

    def _optional_decimal(self, data: dict[str, Any], key: str, aliases: tuple[str, ...] = ()) -> Decimal | None:
        value = self._lookup(data, key, aliases)
        if value is None or value == "":
            return None
        return Decimal(str(value))

    def _optional_bool(self, data: dict[str, Any], key: str, default: bool, aliases: tuple[str, ...] = ()) -> bool:
        value = self._lookup(data, key, aliases)
        if value is None or value == "":
            return default
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "y"}:
            return True
        if text in {"0", "false", "no", "n"}:
            return False
        raise ValidationError(f"Import boolean value for '{key}' must be true or false.")

    def _optional_date(self, data: dict[str, Any], key: str, aliases: tuple[str, ...] = ()) -> date | None:
        value = self._lookup(data, key, aliases)
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value).strip())

    def _optional_int_tuple(self, data: dict[str, Any], key: str, aliases: tuple[str, ...] = ()) -> tuple[int, ...]:
        value = self._lookup(data, key, aliases)
        if value is None or value == "":
            return ()
        if isinstance(value, (list, tuple)):
            return tuple(int(item) for item in value if item != "")
        return (int(value),)

    def _require_permission(self, permission_code: str) -> None:
        if self._permission_service is not None:
            self._permission_service.require_permission(permission_code)

    def _require_company(self, session: Session, company_id: int) -> None:
        if self._company_repository_factory(session).get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

    def _commit_or_translate(self, uow) -> None:
        try:
            uow.commit()
        except IntegrityError as exc:
            raise ConflictError("Inventory import job conflicts with an existing record.") from exc

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
    def _normalize_required(value: str, label: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValidationError(f"{label} is required.")
        return text

    @staticmethod
    def _normalize_optional_text(value: str | None) -> str | None:
        text = (value or "").strip()
        return text or None

    def _normalize_row_status(self, value: str) -> str:
        normalized = (value or "").strip().lower()
        if normalized not in self._ALLOWED_ROW_STATUSES:
            raise ValidationError("Import row status must be valid, invalid, or conflict.")
        return normalized

    @staticmethod
    def _to_dto(job: InventoryImportJob) -> InventoryImportJobDTO:
        return InventoryImportJobDTO(
            id=job.id,
            company_id=job.company_id,
            template_code=job.template_code,
            source_filename=job.source_filename,
            status_code=job.status_code,
            total_rows=job.total_rows,
            valid_rows=job.valid_rows,
            invalid_rows=job.invalid_rows,
            conflict_rows=job.conflict_rows,
            applied_at=job.applied_at,
            applied_by_user_id=job.applied_by_user_id,
            created_by_user_id=job.created_by_user_id,
            preview_json=job.preview_json,
            error_summary=job.error_summary,
            rows=tuple(
                InventoryImportJobRowDTO(
                    id=row.id,
                    job_id=row.job_id,
                    row_number=row.row_number,
                    status_code=row.status_code,
                    normalized_json=row.normalized_json,
                    error_messages_json=row.error_messages_json,
                )
                for row in sorted(job.rows, key=lambda value: value.row_number)
            ),
        )