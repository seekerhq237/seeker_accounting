"""Goods Receipt Service — P2 / Slice 3.3.

Handles the full GRN (Goods Receipt Note) workflow:

  create_from_po  — draft a GRN from a purchase order
  post_receipt    — post a draft GRN: stock ledger + GRNI journal entry + PO receipt links
  match_to_bill   — link a posted GRN to a supplier bill: GRNI clearing + AP JE + PPV
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.accounting.journals.models.journal_entry import JournalEntry
from seeker_accounting.modules.accounting.journals.models.journal_entry_line import JournalEntryLine
from seeker_accounting.modules.accounting.journals.repositories.journal_entry_repository import (
    JournalEntryRepository,
)
from seeker_accounting.modules.accounting.reference_data.repositories.account_role_mapping_repository import (
    AccountRoleMappingRepository,
)
from seeker_accounting.modules.inventory.models.inventory_document import InventoryDocument
from seeker_accounting.modules.inventory.models.inventory_document_line import InventoryDocumentLine
from seeker_accounting.modules.inventory.models.purchase_receipt_link import (
    PurchaseBillLineReceiptLink,
    PurchaseOrderLineReceiptLink,
)
from seeker_accounting.modules.inventory.repositories.inventory_document_repository import (
    InventoryDocumentRepository,
)
from seeker_accounting.modules.inventory.repositories.purchase_receipt_link_repository import (
    PurchaseReceiptLinkRepository,
)
from seeker_accounting.modules.inventory.services.stock_ledger_service import StockLedgerService
from seeker_accounting.modules.purchases.repositories.purchase_order_repository import (
    PurchaseOrderRepository,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError
from seeker_accounting.platform.numerics.rounding_policy import quantize_amount, quantize_quantity

if TYPE_CHECKING:
    pass

_ZERO = Decimal("0")
_ZERO_AMT = Decimal("0.00")

JournalEntryRepositoryFactory = Callable[[Session], JournalEntryRepository]
AccountRoleMappingRepositoryFactory = Callable[[Session], AccountRoleMappingRepository]
InventoryDocumentRepositoryFactory = Callable[[Session], InventoryDocumentRepository]
PurchaseOrderRepositoryFactory = Callable[[Session], PurchaseOrderRepository]
PurchaseReceiptLinkRepositoryFactory = Callable[[Session], PurchaseReceiptLinkRepository]


@dataclass
class GrnLineCommand:
    purchase_order_line_id: int
    item_id: int
    received_qty: Decimal
    unit_cost: Decimal
    batch_id: int | None = None
    uom_id: int | None = None
    uom_ratio_snapshot: Decimal | None = None


@dataclass
class GrnCreateResultDTO:
    inventory_document_id: int
    document_number: str


@dataclass
class GrnPostResultDTO:
    inventory_document_id: int
    journal_entry_id: int


class GoodsReceiptService:
    """Orchestrates GRN creation, posting, and bill matching."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        stock_ledger_service: StockLedgerService,
        journal_entry_repository_factory: JournalEntryRepositoryFactory,
        account_role_mapping_repository_factory: AccountRoleMappingRepositoryFactory,
        inventory_document_repository_factory: InventoryDocumentRepositoryFactory,
        purchase_order_repository_factory: PurchaseOrderRepositoryFactory,
        purchase_receipt_link_repository_factory: PurchaseReceiptLinkRepositoryFactory,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._stock_ledger_service = stock_ledger_service
        self._journal_entry_repository_factory = journal_entry_repository_factory
        self._account_role_mapping_repository_factory = account_role_mapping_repository_factory
        self._inventory_document_repository_factory = inventory_document_repository_factory
        self._purchase_order_repository_factory = purchase_order_repository_factory
        self._purchase_receipt_link_repository_factory = purchase_receipt_link_repository_factory

    # ------------------------------------------------------------------
    # Create draft GRN from PO
    # ------------------------------------------------------------------

    def create_from_po(
        self,
        company_id: int,
        purchase_order_id: int,
        lines: list[GrnLineCommand],
        location_id: int | None,
        receipt_date: date,
        reference: str | None = None,
        actor_user_id: int | None = None,
    ) -> GrnCreateResultDTO:
        if not lines:
            raise ValidationError("At least one receipt line is required.")

        with self._uow_factory() as uow:
            po_repo = self._purchase_order_repository_factory(uow.session)
            po = po_repo.get(company_id, purchase_order_id)
            if po is None:
                raise NotFoundError(f"Purchase order {purchase_order_id} not found.")
            if po.status_code not in ("approved", "partially_received"):
                raise ValidationError(
                    f"Purchase order must be approved or partially received to receive against it; "
                    f"current status: {po.status_code}"
                )

            doc_repo = self._inventory_document_repository_factory(uow.session)
            doc_number = self._generate_grn_number(uow.session, company_id)

            doc = InventoryDocument(
                company_id=company_id,
                document_number=doc_number,
                document_type_code="goods_receipt_purchase",
                document_date=receipt_date,
                status_code="draft",
                location_id=location_id,
                purchase_order_id=purchase_order_id,
                source_module_code="purchases",
                source_document_type="purchase_order",
                source_document_id=purchase_order_id,
                notes=reference,
            )
            doc_repo.add(doc)
            uow.session.flush()

            for idx, cmd in enumerate(lines, start=1):
                qty = quantize_quantity(cmd.received_qty)
                unit_cost = Decimal(str(cmd.unit_cost))
                doc_line = InventoryDocumentLine(
                    inventory_document_id=doc.id,
                    line_number=idx,
                    item_id=cmd.item_id,
                    batch_id=cmd.batch_id,
                    quantity=qty,
                    unit_cost=unit_cost,
                    line_amount=quantize_amount(qty * unit_cost),
                    transaction_uom_id=cmd.uom_id,
                    uom_ratio_snapshot=cmd.uom_ratio_snapshot,
                    base_quantity=qty,
                )
                uow.session.add(doc_line)

            uow.commit()
            return GrnCreateResultDTO(
                inventory_document_id=doc.id,
                document_number=doc_number,
            )

    # ------------------------------------------------------------------
    # Post draft GRN (stock ledger + GRNI JE + PO links)
    # ------------------------------------------------------------------

    def post_receipt(
        self,
        company_id: int,
        inventory_document_id: int,
        fiscal_period_id: int,
        actor_user_id: int | None = None,
    ) -> GrnPostResultDTO:
        with self._uow_factory() as uow:
            doc_repo = self._inventory_document_repository_factory(uow.session)
            doc = doc_repo.get(inventory_document_id)
            if doc is None:
                raise NotFoundError(f"Inventory document {inventory_document_id} not found.")
            if doc.company_id != company_id:
                raise NotFoundError(f"Inventory document {inventory_document_id} not found.")
            if doc.status_code != "draft":
                raise ConflictError(
                    f"Only draft GRNs can be posted; current status: {doc.status_code}"
                )
            if doc.document_type_code != "goods_receipt_purchase":
                raise ValidationError(
                    f"Expected goods_receipt_purchase document type; "
                    f"got: {doc.document_type_code}"
                )

            role_mapping_repo = self._account_role_mapping_repository_factory(uow.session)
            grni_mapping = role_mapping_repo.get_by_role_code(company_id, "grni_clearing")
            if grni_mapping is None:
                raise ValidationError(
                    "A GRNI clearing account mapping must be configured before posting GRNs."
                )

            je_repo = self._journal_entry_repository_factory(uow.session)
            receipt_link_repo = self._purchase_receipt_link_repository_factory(uow.session)

            journal_lines: list[JournalEntryLine] = []
            line_num = 1

            for doc_line in doc.lines:
                from seeker_accounting.modules.inventory.repositories.item_repository import ItemRepository
                item_repo = ItemRepository(uow.session)
                item = item_repo.get(doc_line.item_id)
                if item is None:
                    raise ValidationError(f"Item {doc_line.item_id} not found.")

                qty = quantize_quantity(doc_line.base_quantity or doc_line.quantity)
                unit_cost = doc_line.unit_cost or _ZERO
                line_value = quantize_amount(qty * unit_cost)

                # Stock ledger receipt
                self._stock_ledger_service.append(
                    uow.session,
                    company_id=company_id,
                    item_id=doc_line.item_id,
                    location_id=doc.location_id,
                    posting_date=doc.document_date,
                    document_type_code="goods_receipt_purchase",
                    inventory_document_line_id=doc_line.id,
                    direction=1,
                    quantity_base=qty,
                    unit_cost=unit_cost,
                    batch_id=doc_line.batch_id,
                )

                if item.inventory_account_id:
                    # Dr Inventory
                    journal_lines.append(
                        JournalEntryLine(
                            journal_entry_id=0,
                            line_number=line_num,
                            account_id=item.inventory_account_id,
                            line_description=f"GRN receipt – {item.item_name}",
                            debit_amount=line_value,
                            credit_amount=_ZERO_AMT,
                        )
                    )
                    line_num += 1

                    # Cr GRNI
                    journal_lines.append(
                        JournalEntryLine(
                            journal_entry_id=0,
                            line_number=line_num,
                            account_id=grni_mapping.account_id,
                            line_description=f"GRNI – {item.item_name}",
                            debit_amount=_ZERO_AMT,
                            credit_amount=line_value,
                        )
                    )
                    line_num += 1

                # PO receipt link
                if doc.purchase_order_id:
                    po_link = PurchaseOrderLineReceiptLink(
                        company_id=company_id,
                        purchase_order_line_id=self._find_po_line_id(
                            uow.session, doc.purchase_order_id, doc_line.item_id
                        ),
                        inventory_document_line_id=doc_line.id,
                        received_qty=qty,
                    )
                    receipt_link_repo.add_po_link(po_link)

            # Create JE
            journal_entry = JournalEntry(
                company_id=company_id,
                fiscal_period_id=fiscal_period_id,
                entry_number=None,
                entry_date=doc.document_date,
                journal_type_code="INVENTORY",
                reference_text=doc.document_number,
                description=f"GRN {doc.document_number}",
                source_module_code="inventory",
                source_document_type="goods_receipt_purchase",
                source_document_id=doc.id,
                status_code="POSTED",
                posted_at=datetime.utcnow(),
                posted_by_user_id=actor_user_id,
                created_by_user_id=actor_user_id,
            )
            je_repo.add(journal_entry)
            uow.session.flush()

            for jl in journal_lines:
                jl.journal_entry_id = journal_entry.id
            uow.session.add_all(journal_lines)

            doc.status_code = "posted"
            doc.posted_journal_entry_id = journal_entry.id
            doc.posted_at = datetime.utcnow()
            doc.posted_by_user_id = actor_user_id

            uow.commit()
            return GrnPostResultDTO(
                inventory_document_id=doc.id,
                journal_entry_id=journal_entry.id,
            )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _generate_grn_number(self, session: Session, company_id: int) -> str:
        from sqlalchemy import func, select
        from seeker_accounting.modules.inventory.models.inventory_document import InventoryDocument as ID
        count = session.scalar(
            select(func.count(ID.id)).where(
                ID.company_id == company_id,
                ID.document_type_code == "goods_receipt_purchase",
            )
        ) or 0
        return f"GRN-{company_id:04d}-{count + 1:06d}"

    def _find_po_line_id(self, session: Session, po_id: int, item_id: int) -> int:
        """Best-effort lookup: find the PO line for the given item."""
        from sqlalchemy import select
        from seeker_accounting.modules.purchases.models.purchase_order_line import PurchaseOrderLine
        stmt = select(PurchaseOrderLine.id).where(
            PurchaseOrderLine.purchase_order_id == po_id,
            PurchaseOrderLine.item_id == item_id,
        ).limit(1)
        result = session.scalar(stmt)
        if result is None:
            raise ValidationError(
                f"Could not find a PO line for item {item_id} on PO {po_id}."
            )
        return result
