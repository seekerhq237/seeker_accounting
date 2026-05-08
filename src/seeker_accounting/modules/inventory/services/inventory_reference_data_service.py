"""Service maintaining the inventory reference taxonomy.

Phase 0 / Slice 1.4 — owns the per-company seeding of the document-type
catalog (21 codes) and the standard reason-code library, plus CRUD on
reason codes. Document types are seeded as immutable taxonomy and not
exposed through CRUD on the UI in this slice.
"""

from __future__ import annotations
import logging

from typing import TYPE_CHECKING, Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import (
    PermissionService,
)
from seeker_accounting.modules.companies.repositories.company_repository import (
    CompanyRepository,
)
from seeker_accounting.modules.inventory.dto.inventory_reference_commands import (
    CreateInventoryReasonCodeCommand,
    UpdateInventoryReasonCodeCommand,
)
from seeker_accounting.modules.inventory.dto.inventory_reference_dto import (
    InventoryDocumentTypeDTO,
    InventoryReasonCodeDTO,
)
from seeker_accounting.modules.inventory.models.inventory_document_type import (
    InventoryDocumentType,
)
from seeker_accounting.modules.inventory.models.inventory_reason_code import (
    InventoryReasonCode,
)
from seeker_accounting.modules.inventory.repositories.inventory_document_type_repository import (
    InventoryDocumentTypeRepository,
)
from seeker_accounting.modules.inventory.repositories.inventory_reason_code_repository import (
    InventoryReasonCodeRepository,
)
from seeker_accounting.platform.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)

if TYPE_CHECKING:  # pragma: no cover
    from seeker_accounting.modules.audit.services.audit_service import AuditService


CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
DocTypeRepoFactory = Callable[[Session], InventoryDocumentTypeRepository]
ReasonRepoFactory = Callable[[Session], InventoryReasonCodeRepository]


# ---------------------------------------------------------------------------
# Standard taxonomy — frozen at module level so the migration and the
# service share the same source of truth.
# ---------------------------------------------------------------------------

# (code, name, direction_sign, is_transfer, is_reversal,
#  requires_unit_cost_on_line, requires_reason_code, posts_to_inventory_account)
STANDARD_DOCUMENT_TYPES: tuple[tuple[str, str, int, bool, bool, bool, bool, bool], ...] = (
    ("goods_receipt_purchase", "Goods Receipt (Purchase)", 1, False, False, True, False, True),
    ("goods_receipt_other", "Goods Receipt (Other)", 1, False, False, True, False, True),
    ("goods_issue_sale", "Goods Issue (Sale)", -1, False, False, False, False, True),
    ("goods_issue_consumption", "Goods Issue (Consumption)", -1, False, False, False, False, True),
    ("transfer_out", "Transfer Out", -1, True, False, False, False, True),
    ("transfer_in", "Transfer In", 1, True, False, False, False, True),
    ("transfer_in_transit", "Transfer In Transit", 0, True, False, False, False, True),
    ("adjustment_increase", "Adjustment (Increase)", 1, False, False, True, True, True),
    ("adjustment_decrease", "Adjustment (Decrease)", -1, False, False, False, True, True),
    ("scrap", "Scrap", -1, False, False, False, True, True),
    ("wastage", "Wastage", -1, False, False, False, True, True),
    ("count_gain", "Count Gain", 1, False, False, True, True, True),
    ("count_loss", "Count Loss", -1, False, False, False, True, True),
    ("opening_balance", "Opening Balance", 1, False, False, True, False, True),
    ("production_receipt", "Production Receipt", 1, False, False, True, False, True),
    ("production_issue", "Production Issue", -1, False, False, False, False, True),
    ("customer_return", "Customer Return", 1, False, True, False, False, True),
    ("supplier_return", "Supplier Return", -1, False, True, False, False, True),
    ("revaluation", "Revaluation", 0, False, False, True, True, True),
    ("consignment_in", "Consignment In", 1, False, False, True, False, True),
    ("consignment_out", "Consignment Out", -1, False, False, False, False, True),
)


# (code, name)
STANDARD_REASON_CODES: tuple[tuple[str, str], ...] = (
    ("damaged_goods", "Damaged Goods"),
    ("expiry", "Expiry"),
    ("count_variance", "Physical Count Variance"),
    ("breakage", "Breakage"),
    ("theft_loss", "Theft / Loss"),
    ("supplier_quality", "Supplier Quality Issue"),
    ("opening_balance", "Opening Balance"),
    ("scrap_disposal", "Scrap Disposal"),
    ("internal_use", "Internal Use"),
    ("revaluation", "Inventory Revaluation"),
    ("other", "Other"),
)


class InventoryReferenceDataService:
    """Seeds and exposes the inventory document-type and reason-code catalogs."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        document_type_repository_factory: DocTypeRepoFactory,
        reason_code_repository_factory: ReasonRepoFactory,
        permission_service: PermissionService,
        audit_service: "AuditService | None" = None,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._company_repo_factory = company_repository_factory
        self._doc_type_repo_factory = document_type_repository_factory
        self._reason_repo_factory = reason_code_repository_factory
        self._permission_service = permission_service
        self._audit_service = audit_service

    # ------------------------------------------------------------------
    # Document types (read-only catalog)
    # ------------------------------------------------------------------

    def list_document_types(
        self, company_id: int, active_only: bool = True
    ) -> list[InventoryDocumentTypeDTO]:
        self._permission_service.require_permission("inventory.document_types.view")
        with self._uow_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._doc_type_repo_factory(uow.session)
            rows = repo.list_by_company(company_id, active_only=active_only)
            return [self._to_doc_type_dto(r) for r in rows]

    def ensure_document_types_seeded(self, company_id: int) -> int:
        """Idempotently seed the standard document-type catalog for a company.

        Returns the number of rows inserted in this call.
        """
        inserted = 0
        with self._uow_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._doc_type_repo_factory(uow.session)
            for spec in STANDARD_DOCUMENT_TYPES:
                code = spec[0]
                if repo.get_by_code(company_id, code) is not None:
                    continue
                repo.add(
                    InventoryDocumentType(
                        company_id=company_id,
                        code=code,
                        name=spec[1],
                        direction_sign=spec[2],
                        is_transfer=spec[3],
                        is_reversal=spec[4],
                        requires_unit_cost_on_line=spec[5],
                        requires_reason_code=spec[6],
                        posts_to_inventory_account=spec[7],
                        is_active=True,
                    )
                )
                inserted += 1
            uow.commit()
        if inserted and self._audit_service is not None:
            self._record_audit(
                company_id,
                "INVENTORY_DOCUMENT_TYPE_SEEDED",
                "InventoryDocumentType",
                None,
                f"Seeded {inserted} inventory document type(s).",
            )
        return inserted

    # ------------------------------------------------------------------
    # Reason codes
    # ------------------------------------------------------------------

    def list_reason_codes(
        self, company_id: int, active_only: bool = False
    ) -> list[InventoryReasonCodeDTO]:
        self._permission_service.require_permission("inventory.reason_codes.view")
        with self._uow_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._reason_repo_factory(uow.session)
            return [
                self._to_reason_dto(r)
                for r in repo.list_by_company(company_id, active_only=active_only)
            ]

    def ensure_standard_reason_codes(self, company_id: int) -> int:
        inserted = 0
        with self._uow_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._reason_repo_factory(uow.session)
            for code, name in STANDARD_REASON_CODES:
                if repo.get_by_code(company_id, code) is not None:
                    continue
                repo.add(
                    InventoryReasonCode(
                        company_id=company_id,
                        code=code,
                        name=name,
                        is_active=True,
                    )
                )
                inserted += 1
            uow.commit()
        return inserted

    def create_reason_code(
        self, company_id: int, command: CreateInventoryReasonCodeCommand
    ) -> InventoryReasonCodeDTO:
        self._permission_service.require_permission("inventory.reason_codes.manage")
        self._validate_reason_fields(command.code, command.name)
        with self._uow_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._reason_repo_factory(uow.session)
            if repo.get_by_code(company_id, command.code.strip()) is not None:
                raise ConflictError(
                    f"Reason code '{command.code}' already exists for this company."
                )
            row = InventoryReasonCode(
                company_id=company_id,
                code=command.code.strip(),
                name=command.name.strip(),
                description=command.description,
                is_active=True,
            )
            repo.add(row)
            uow.commit()
            self._record_audit(
                company_id,
                "INVENTORY_REASON_CODE_CREATED",
                "InventoryReasonCode",
                row.id,
                f"Created reason code '{row.code}'.",
            )
            return self._to_reason_dto(row)

    def update_reason_code(
        self,
        company_id: int,
        reason_id: int,
        command: UpdateInventoryReasonCodeCommand,
    ) -> InventoryReasonCodeDTO:
        self._permission_service.require_permission("inventory.reason_codes.manage")
        self._validate_reason_fields(command.code, command.name)
        with self._uow_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._reason_repo_factory(uow.session)
            row = repo.get_by_id(company_id, reason_id)
            if row is None:
                raise NotFoundError(
                    f"Reason code with id {reason_id} was not found."
                )
            new_code = command.code.strip()
            if new_code != row.code and repo.get_by_code(company_id, new_code) is not None:
                raise ConflictError(
                    f"Reason code '{new_code}' already exists for this company."
                )
            row.code = new_code
            row.name = command.name.strip()
            row.description = command.description
            row.is_active = command.is_active
            repo.save(row)
            uow.commit()
            self._record_audit(
                company_id,
                "INVENTORY_REASON_CODE_UPDATED",
                "InventoryReasonCode",
                row.id,
                f"Updated reason code '{row.code}'.",
            )
            return self._to_reason_dto(row)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _require_company(self, session: Session, company_id: int) -> None:
        repo = self._company_repo_factory(session)
        if repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

    def _validate_reason_fields(self, code: str, name: str) -> None:
        if not code or not code.strip():
            raise ValidationError("Reason code is required.")
        if not name or not name.strip():
            raise ValidationError("Reason name is required.")

    def _to_doc_type_dto(self, row: InventoryDocumentType) -> InventoryDocumentTypeDTO:
        return InventoryDocumentTypeDTO(
            id=row.id,
            company_id=row.company_id,
            code=row.code,
            name=row.name,
            description=row.description,
            direction_sign=row.direction_sign,
            is_transfer=row.is_transfer,
            is_reversal=row.is_reversal,
            requires_unit_cost_on_line=row.requires_unit_cost_on_line,
            requires_reason_code=row.requires_reason_code,
            posts_to_inventory_account=row.posts_to_inventory_account,
            is_active=row.is_active,
        )

    def _to_reason_dto(self, row: InventoryReasonCode) -> InventoryReasonCodeDTO:
        return InventoryReasonCodeDTO(
            id=row.id,
            company_id=row.company_id,
            code=row.code,
            name=row.name,
            description=row.description,
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
            logging.getLogger(__name__).warning("Audit event failed", exc_info=True)
