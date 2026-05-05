"""Stock transfer service.

Per ``docs/inventory_upgrade_plan.md`` Slice 2.3: first-class transfer
documents with optional in-transit handling.

Two transfer modes:

``use_in_transit=False`` (direct transfer):
    Creates one ``transfer_out`` document for the source location and one
    ``transfer_in`` document for the destination location.  Both are posted
    immediately in a single unit-of-work.  Net GL effect is zero.

``use_in_transit=True`` (in-transit transfer):
    Creates a single ``transfer_in_transit`` document that:
    * Issues stock from the source location (status = in_transit).
    * Does NOT yet credit the destination.
    The caller later calls ``receive_in_transit(doc_id)`` which creates
    a matching ``transfer_in`` document and marks the originating document
    ``completed``.

Both paths write immutable stock ledger entries via
``InventoryPostingService``; the transfer service delegates posting to avoid
duplicating GL logic.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.inventory.dto.inventory_document_commands import (
    CreateInventoryDocumentCommand,
    InventoryDocumentLineCommand,
)
from seeker_accounting.modules.inventory.dto.stock_transfer_dto import (
    CreateTransferCommand,
    TransferResultDTO,
)
from seeker_accounting.modules.inventory.repositories.inventory_document_repository import (
    InventoryDocumentRepository,
)
from seeker_accounting.modules.inventory.repositories.inventory_location_repository import (
    InventoryLocationRepository,
)
from seeker_accounting.modules.inventory.repositories.item_repository import ItemRepository
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.inventory.services.inventory_document_service import (
        InventoryDocumentService,
    )
    from seeker_accounting.modules.inventory.services.inventory_posting_service import (
        InventoryPostingService,
    )

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
InventoryDocumentRepositoryFactory = Callable[[Session], InventoryDocumentRepository]
InventoryLocationRepositoryFactory = Callable[[Session], InventoryLocationRepository]
ItemRepositoryFactory = Callable[[Session], ItemRepository]


class StockTransferService:
    """Orchestrates stock movements between locations."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        inventory_document_repository_factory: InventoryDocumentRepositoryFactory,
        inventory_location_repository_factory: InventoryLocationRepositoryFactory,
        item_repository_factory: ItemRepositoryFactory,
        inventory_document_service: "InventoryDocumentService",
        inventory_posting_service: "InventoryPostingService",
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory
        self._doc_repo_factory = inventory_document_repository_factory
        self._loc_repo_factory = inventory_location_repository_factory
        self._item_repo_factory = item_repository_factory
        self._doc_service = inventory_document_service
        self._posting_service = inventory_posting_service

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_and_post_transfer(
        self,
        company_id: int,
        cmd: CreateTransferCommand,
        actor_user_id: int | None = None,
    ) -> TransferResultDTO:
        """Create and immediately post a direct or in-transit transfer."""
        with self._unit_of_work_factory() as uow:
            company_repo = self._company_repository_factory(uow.session)
            if company_repo.get_by_id(company_id) is None:
                raise NotFoundError(f"Company {company_id} not found.")

            loc_repo = self._loc_repo_factory(uow.session)
            from_loc = loc_repo.get_by_id(company_id, cmd.from_location_id)
            to_loc = loc_repo.get_by_id(company_id, cmd.to_location_id)
            if from_loc is None:
                raise NotFoundError(f"Source location {cmd.from_location_id} not found.")
            if to_loc is None:
                raise NotFoundError(f"Destination location {cmd.to_location_id} not found.")
            if cmd.from_location_id == cmd.to_location_id:
                raise ValidationError("Source and destination locations must be different.")
            if not cmd.lines:
                raise ValidationError("A transfer must have at least one line.")

            uow.commit()

        if cmd.use_in_transit:
            return self._post_in_transit_transfer(company_id, cmd, actor_user_id)
        return self._post_direct_transfer(company_id, cmd, actor_user_id)

    def receive_in_transit(
        self,
        company_id: int,
        transit_document_id: int,
        receive_date=None,
        actor_user_id: int | None = None,
    ) -> TransferResultDTO:
        """Complete an in-transit transfer by receiving stock at the destination.

        Creates a ``transfer_in`` document mirroring the original
        ``transfer_in_transit`` document's lines, posts it, and marks the
        originating document ``completed``.
        """
        with self._unit_of_work_factory() as uow:
            doc_repo = self._doc_repo_factory(uow.session)
            transit_doc = doc_repo.get_detail(company_id, transit_document_id)
            if transit_doc is None:
                raise NotFoundError(f"Transfer document {transit_document_id} not found.")
            if transit_doc.document_type_code != "transfer_in_transit":
                raise ValidationError("Document is not a transfer_in_transit document.")
            if transit_doc.transfer_status_code != "in_transit":
                raise ValidationError(
                    f"Transfer is not in-transit (status={transit_doc.transfer_status_code!r})."
                )
            if transit_doc.to_location_id is None:
                raise ValidationError("Transfer document has no destination location set.")

            receive_date = receive_date or transit_doc.document_date

            # Build mirror lines for transfer_in at destination
            lines = tuple(
                InventoryDocumentLineCommand(
                    item_id=line.item_id,
                    quantity=line.quantity,
                    unit_cost=line.unit_cost,
                    batch_id=line.batch_id,
                    serial_ids=tuple(link.serial_id for link in line.serial_links),
                    counterparty_account_id=line.counterparty_account_id,
                )
                for line in transit_doc.lines
            )
            uow.commit()

        # Create the matching receive document
        receive_draft = self._doc_service.create_draft_document(
            company_id,
            CreateInventoryDocumentCommand(
                document_type_code="transfer_in",
                document_date=receive_date,
                location_id=transit_doc.to_location_id,
                reference_number=transit_doc.document_number,
                notes=f"Received from in-transit: {transit_doc.document_number}",
                reason_code_id=None,
                source_module_code="inventory",
                source_document_type="inventory_transfer",
                source_document_id=transit_document_id,
                lines=lines,
            ),
        )
        receive_result = self._posting_service.post_inventory_document(
            company_id, receive_draft.id, actor_user_id=actor_user_id
        )

        # Mark the originating document completed
        with self._unit_of_work_factory() as uow:
            doc_repo = self._doc_repo_factory(uow.session)
            transit_doc = doc_repo.get_detail(company_id, transit_document_id)
            if transit_doc is not None:
                transit_doc.transfer_status_code = "completed"
                doc_repo.save(transit_doc)
            uow.commit()

        return TransferResultDTO(
            transfer_document_id=transit_document_id,
            transfer_status_code="completed",
            receive_document_id=receive_draft.id,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _post_direct_transfer(
        self,
        company_id: int,
        cmd: CreateTransferCommand,
        actor_user_id: int | None,
    ) -> TransferResultDTO:
        """Create transfer_out and transfer_in, post both immediately."""
        # Build lines for the outbound leg. Unit cost must come from the source
        # location's current layers; we let the posting service resolve it.
        out_lines = tuple(
            InventoryDocumentLineCommand(
                item_id=l.item_id,
                quantity=l.quantity,
                unit_cost=None,  # issue at current avg/FIFO
                batch_id=l.batch_id,
                serial_ids=l.serial_ids,
                counterparty_account_id=l.counterparty_account_id,
                contract_id=l.contract_id,
                project_id=l.project_id,
            )
            for l in cmd.lines
        )

        out_draft = self._doc_service.create_draft_document(
            company_id,
            CreateInventoryDocumentCommand(
                document_type_code="transfer_out",
                document_date=cmd.transfer_date,
                location_id=cmd.from_location_id,
                reference_number=cmd.reference_number,
                notes=cmd.notes,
                reason_code_id=None,
                source_module_code="inventory",
                source_document_type="inventory_transfer",
                source_document_id=None,
                lines=out_lines,
            ),
        )
        out_result = self._posting_service.post_inventory_document(
            company_id, out_draft.id, actor_user_id=actor_user_id
        )

        # Build inbound lines — use the unit costs resolved during outbound posting.
        # We re-load the posted out doc to get the computed line amounts.
        with self._unit_of_work_factory() as uow:
            doc_repo = self._doc_repo_factory(uow.session)
            posted_out = doc_repo.get_detail(company_id, out_draft.id)
            in_lines = tuple(
                InventoryDocumentLineCommand(
                    item_id=line.item_id,
                    quantity=line.quantity,
                    unit_cost=line.unit_cost or Decimal("0"),
                    batch_id=line.batch_id,
                    serial_ids=tuple(link.serial_id for link in line.serial_links),
                    counterparty_account_id=line.counterparty_account_id,
                    contract_id=line.contract_id,
                    project_id=line.project_id,
                )
                for line in (posted_out.lines if posted_out else [])
            )
            uow.commit()

        in_draft = self._doc_service.create_draft_document(
            company_id,
            CreateInventoryDocumentCommand(
                document_type_code="transfer_in",
                document_date=cmd.transfer_date,
                location_id=cmd.to_location_id,
                reference_number=cmd.reference_number,
                notes=cmd.notes,
                reason_code_id=None,
                source_module_code="inventory",
                source_document_type="inventory_transfer",
                source_document_id=out_draft.id,
                lines=in_lines,
            ),
        )
        self._posting_service.post_inventory_document(
            company_id, in_draft.id, actor_user_id=actor_user_id
        )

        # Stamp transfer metadata on originating document
        with self._unit_of_work_factory() as uow:
            doc_repo = self._doc_repo_factory(uow.session)
            out_doc = doc_repo.get_detail(company_id, out_draft.id)
            if out_doc is not None:
                out_doc.from_location_id = cmd.from_location_id
                out_doc.to_location_id = cmd.to_location_id
                out_doc.transfer_status_code = "completed"
                doc_repo.save(out_doc)
            uow.commit()

        return TransferResultDTO(
            transfer_document_id=out_draft.id,
            transfer_status_code="completed",
            receive_document_id=in_draft.id,
        )

    def _post_in_transit_transfer(
        self,
        company_id: int,
        cmd: CreateTransferCommand,
        actor_user_id: int | None,
    ) -> TransferResultDTO:
        """Create a transfer_in_transit document, post the outbound leg only."""
        transit_lines = tuple(
            InventoryDocumentLineCommand(
                item_id=l.item_id,
                quantity=l.quantity,
                unit_cost=None,
                batch_id=l.batch_id,
                serial_ids=l.serial_ids,
                counterparty_account_id=l.counterparty_account_id,
                contract_id=l.contract_id,
                project_id=l.project_id,
            )
            for l in cmd.lines
        )
        transit_draft = self._doc_service.create_draft_document(
            company_id,
            CreateInventoryDocumentCommand(
                document_type_code="transfer_in_transit",
                document_date=cmd.transfer_date,
                location_id=cmd.from_location_id,
                reference_number=cmd.reference_number,
                notes=cmd.notes,
                reason_code_id=None,
                source_module_code="inventory",
                source_document_type="inventory_transfer",
                source_document_id=None,
                lines=transit_lines,
            ),
        )
        # Stamp from/to and mark in_transit before posting
        with self._unit_of_work_factory() as uow:
            doc_repo = self._doc_repo_factory(uow.session)
            transit_doc = doc_repo.get_detail(company_id, transit_draft.id)
            if transit_doc is not None:
                transit_doc.from_location_id = cmd.from_location_id
                transit_doc.to_location_id = cmd.to_location_id
                transit_doc.transfer_status_code = "in_transit"
                doc_repo.save(transit_doc)
            uow.commit()

        self._posting_service.post_inventory_document(
            company_id, transit_draft.id, actor_user_id=actor_user_id
        )

        return TransferResultDTO(
            transfer_document_id=transit_draft.id,
            transfer_status_code="in_transit",
            receive_document_id=None,
        )
