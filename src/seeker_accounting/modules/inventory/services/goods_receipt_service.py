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
from seeker_accounting.modules.accounting.fiscal_periods.repositories.fiscal_period_repository import (
    FiscalPeriodRepository,
)
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
from seeker_accounting.modules.purchases.repositories.purchase_bill_repository import (
    PurchaseBillRepository,
)
from seeker_accounting.modules.purchases.repositories.purchase_order_repository import (
    PurchaseOrderRepository,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, PeriodLockedError, ValidationError
from seeker_accounting.platform.numerics.rounding_policy import quantize_amount, quantize_quantity

if TYPE_CHECKING:
    pass

_ZERO = Decimal("0")
_ZERO_AMT = Decimal("0.00")

JournalEntryRepositoryFactory = Callable[[Session], JournalEntryRepository]
AccountRoleMappingRepositoryFactory = Callable[[Session], AccountRoleMappingRepository]
FiscalPeriodRepositoryFactory = Callable[[Session], FiscalPeriodRepository]
InventoryDocumentRepositoryFactory = Callable[[Session], InventoryDocumentRepository]
PurchaseBillRepositoryFactory = Callable[[Session], PurchaseBillRepository]
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


@dataclass
class GrnBillMatchLineCommand:
    purchase_bill_line_id: int
    inventory_document_line_id: int
    matched_qty: Decimal


@dataclass
class GrnBillMatchResultDTO:
    purchase_bill_id: int
    journal_entry_id: int
    matched_line_count: int
    grni_cleared_amount: Decimal
    bill_matched_amount: Decimal
    purchase_price_variance_amount: Decimal


@dataclass(frozen=True)
class GrnBillMatchBillLineDTO:
    purchase_bill_line_id: int
    line_number: int
    description: str
    item_id: int | None
    quantity: Decimal
    matched_qty: Decimal
    available_qty: Decimal
    unit_cost: Decimal | None
    line_subtotal_amount: Decimal


@dataclass(frozen=True)
class GrnBillMatchReceiptLineDTO:
    inventory_document_line_id: int
    inventory_document_id: int
    document_number: str
    receipt_date: date
    item_id: int
    item_code: str
    item_name: str
    received_qty: Decimal
    matched_qty: Decimal
    available_qty: Decimal
    unit_cost: Decimal
    available_amount: Decimal


@dataclass(frozen=True)
class GrnBillMatchOptionsDTO:
    purchase_bill_id: int
    bill_number: str
    bill_date: date
    bill_status_code: str
    bill_lines: tuple[GrnBillMatchBillLineDTO, ...]
    receipt_lines: tuple[GrnBillMatchReceiptLineDTO, ...]


class GoodsReceiptService:
    """Orchestrates GRN creation, posting, and bill matching."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        stock_ledger_service: StockLedgerService,
        journal_entry_repository_factory: JournalEntryRepositoryFactory,
        account_role_mapping_repository_factory: AccountRoleMappingRepositoryFactory,
        inventory_document_repository_factory: InventoryDocumentRepositoryFactory,
        purchase_bill_repository_factory: PurchaseBillRepositoryFactory,
        purchase_order_repository_factory: PurchaseOrderRepositoryFactory,
        purchase_receipt_link_repository_factory: PurchaseReceiptLinkRepositoryFactory,
        fiscal_period_repository_factory: FiscalPeriodRepositoryFactory | None = None,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._stock_ledger_service = stock_ledger_service
        self._journal_entry_repository_factory = journal_entry_repository_factory
        self._account_role_mapping_repository_factory = account_role_mapping_repository_factory
        self._inventory_document_repository_factory = inventory_document_repository_factory
        self._purchase_bill_repository_factory = purchase_bill_repository_factory
        self._purchase_order_repository_factory = purchase_order_repository_factory
        self._purchase_receipt_link_repository_factory = purchase_receipt_link_repository_factory
        self._fiscal_period_repository_factory = fiscal_period_repository_factory

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
            doc = doc_repo.get_detail(company_id, inventory_document_id)
            if doc is None:
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
    # Match posted GRNs to a posted supplier bill
    # ------------------------------------------------------------------

    def match_to_bill(
        self,
        company_id: int,
        purchase_bill_id: int,
        lines: list[GrnBillMatchLineCommand],
        fiscal_period_id: int | None = None,
        actor_user_id: int | None = None,
    ) -> GrnBillMatchResultDTO:
        if not lines:
            raise ValidationError("At least one GRN line match is required.")

        with self._uow_factory() as uow:
            bill_repo = self._purchase_bill_repository_factory(uow.session)
            doc_repo = self._inventory_document_repository_factory(uow.session)
            link_repo = self._purchase_receipt_link_repository_factory(uow.session)
            role_mapping_repo = self._account_role_mapping_repository_factory(uow.session)
            journal_repo = self._journal_entry_repository_factory(uow.session)

            bill = bill_repo.get_detail(company_id, purchase_bill_id)
            if bill is None:
                raise NotFoundError(f"Purchase bill {purchase_bill_id} not found.")
            if bill.status_code != "posted":
                raise ValidationError(
                    "Only posted purchase bills can be matched to GRNs. "
                    "Post the bill first so AP and tax facts remain owned by purchase bill posting."
                )

            resolved_fiscal_period_id = self._resolve_fiscal_period_id(
                uow.session,
                company_id=company_id,
                bill_date=bill.bill_date,
                fiscal_period_id=fiscal_period_id,
            )

            grni_mapping = role_mapping_repo.get_by_role_code(company_id, "grni_clearing")
            if grni_mapping is None:
                raise ValidationError(
                    "A GRNI clearing account mapping must be configured before matching GRNs to bills."
                )

            bill_lines_by_id = {line.id: line for line in bill.lines}
            doc_line_ids = [cmd.inventory_document_line_id for cmd in lines]
            doc_lines_by_id = {
                line.id: line
                for line in doc_repo.list_lines_by_ids(company_id, doc_line_ids)
            }

            pair_keys: set[tuple[int, int]] = set()
            pending_doc_qty: dict[int, Decimal] = {}
            pending_bill_qty: dict[int, Decimal] = {}
            match_links: list[PurchaseBillLineReceiptLink] = []
            journal_lines: list[JournalEntryLine] = []
            line_number = 1
            total_grni = _ZERO_AMT
            total_bill = _ZERO_AMT
            net_ppv = _ZERO_AMT
            ppv_mapping = None

            for idx, command in enumerate(lines, start=1):
                bill_line = bill_lines_by_id.get(command.purchase_bill_line_id)
                if bill_line is None:
                    raise ValidationError(f"Bill line on match {idx} does not belong to purchase bill {purchase_bill_id}.")

                doc_line = doc_lines_by_id.get(command.inventory_document_line_id)
                if doc_line is None:
                    raise ValidationError(f"GRN line on match {idx} was not found for this company.")

                doc = doc_line.inventory_document
                if doc.document_type_code != "goods_receipt_purchase" or doc.status_code != "posted":
                    raise ValidationError(
                        f"GRN line on match {idx} must belong to a posted goods receipt."
                    )
                if bill_line.item_id is not None and bill_line.item_id != doc_line.item_id:
                    raise ValidationError(
                        f"Bill line {bill_line.id} item does not match GRN line {doc_line.id}."
                    )

                pair_key = (bill_line.id, doc_line.id)
                if pair_key in pair_keys:
                    raise ConflictError("The same bill line and GRN line pair cannot be matched twice.")
                pair_keys.add(pair_key)

                existing_doc_links = link_repo.list_bill_links_for_document(doc_line.id)
                if any(link.purchase_bill_line_id == bill_line.id for link in existing_doc_links):
                    raise ConflictError(
                        f"Bill line {bill_line.id} is already matched to GRN line {doc_line.id}."
                    )
                existing_bill_links = link_repo.list_bill_links_for_bill_line(company_id, bill_line.id)

                matched_qty = self._require_positive_quantity(command.matched_qty, f"Matched quantity on line {idx}")
                doc_available = self._available_quantity(
                    total_quantity=self._document_line_quantity(doc_line),
                    existing_links=existing_doc_links,
                    pending_quantity=pending_doc_qty.get(doc_line.id, _ZERO),
                )
                bill_available = self._available_quantity(
                    total_quantity=self._bill_line_quantity(bill_line),
                    existing_links=existing_bill_links,
                    pending_quantity=pending_bill_qty.get(bill_line.id, _ZERO),
                )
                if matched_qty > doc_available:
                    raise ValidationError(
                        f"Matched quantity for GRN line {doc_line.id} exceeds the available receipt quantity."
                    )
                if matched_qty > bill_available:
                    raise ValidationError(
                        f"Matched quantity for bill line {bill_line.id} exceeds the available bill quantity."
                    )

                receipt_amount = self._receipt_amount_for_quantity(doc_line, matched_qty)
                bill_amount = self._bill_amount_for_quantity(bill_line, matched_qty)
                variance = quantize_amount(bill_amount - receipt_amount)

                journal_lines.append(
                    JournalEntryLine(
                        journal_entry_id=0,
                        line_number=line_number,
                        account_id=grni_mapping.account_id,
                        line_description=f"GRNI clear - Bill {bill.bill_number} / GRN line {doc_line.id}",
                        debit_amount=receipt_amount,
                        credit_amount=_ZERO_AMT,
                    )
                )
                line_number += 1

                if bill_line.expense_account_id is None:
                    raise ValidationError(
                        f"Bill line {bill_line.line_number} must have an expense account to reverse posted bill cost."
                    )
                journal_lines.append(
                    JournalEntryLine(
                        journal_entry_id=0,
                        line_number=line_number,
                        account_id=bill_line.expense_account_id,
                        line_description=f"Reverse bill cost - Bill {bill.bill_number} / line {bill_line.line_number}",
                        debit_amount=_ZERO_AMT,
                        credit_amount=bill_amount,
                        contract_id=bill_line.contract_id or bill.contract_id,
                        project_id=bill_line.project_id or bill.project_id,
                        project_job_id=bill_line.project_job_id,
                        project_cost_code_id=bill_line.project_cost_code_id,
                    )
                )
                line_number += 1

                if variance != _ZERO_AMT:
                    if ppv_mapping is None:
                        ppv_mapping = role_mapping_repo.get_by_role_code(
                            company_id, "purchase_price_variance"
                        )
                        if ppv_mapping is None:
                            raise ValidationError(
                                "A purchase price variance account mapping must be configured "
                                "before matching bill costs that differ from receipt costs."
                            )
                    journal_lines.append(
                        JournalEntryLine(
                            journal_entry_id=0,
                            line_number=line_number,
                            account_id=ppv_mapping.account_id,
                            line_description=f"PPV - Bill {bill.bill_number} / GRN line {doc_line.id}",
                            debit_amount=variance if variance > _ZERO_AMT else _ZERO_AMT,
                            credit_amount=abs(variance) if variance < _ZERO_AMT else _ZERO_AMT,
                        )
                    )
                    line_number += 1

                match_links.append(
                    PurchaseBillLineReceiptLink(
                        company_id=company_id,
                        purchase_bill_line_id=bill_line.id,
                        inventory_document_line_id=doc_line.id,
                        matched_qty=matched_qty,
                        matched_amount=bill_amount,
                    )
                )
                pending_doc_qty[doc_line.id] = pending_doc_qty.get(doc_line.id, _ZERO) + matched_qty
                pending_bill_qty[bill_line.id] = pending_bill_qty.get(bill_line.id, _ZERO) + matched_qty
                total_grni = quantize_amount(total_grni + receipt_amount)
                total_bill = quantize_amount(total_bill + bill_amount)
                net_ppv = quantize_amount(net_ppv + variance)

            journal_entry = JournalEntry(
                company_id=company_id,
                fiscal_period_id=resolved_fiscal_period_id,
                entry_number=None,
                entry_date=bill.bill_date,
                journal_type_code="PURCHASE",
                reference_text=bill.bill_number,
                description=f"GRN match for bill {bill.bill_number}",
                source_module_code="inventory",
                source_document_type="goods_receipt_bill_match",
                source_document_id=bill.id,
                status_code="POSTED",
                posted_at=datetime.utcnow(),
                posted_by_user_id=actor_user_id,
                created_by_user_id=actor_user_id,
            )
            journal_repo.add(journal_entry)
            uow.session.flush()

            for journal_line in journal_lines:
                journal_line.journal_entry_id = journal_entry.id
            uow.session.add_all(journal_lines)
            for match_link in match_links:
                link_repo.add_bill_link(match_link)

            uow.commit()
            return GrnBillMatchResultDTO(
                purchase_bill_id=bill.id,
                journal_entry_id=journal_entry.id,
                matched_line_count=len(match_links),
                grni_cleared_amount=total_grni,
                bill_matched_amount=total_bill,
                purchase_price_variance_amount=net_ppv,
            )

    def get_match_options(
        self,
        company_id: int,
        purchase_bill_id: int,
    ) -> GrnBillMatchOptionsDTO:
        with self._uow_factory() as uow:
            bill_repo = self._purchase_bill_repository_factory(uow.session)
            doc_repo = self._inventory_document_repository_factory(uow.session)
            link_repo = self._purchase_receipt_link_repository_factory(uow.session)

            bill = bill_repo.get_detail(company_id, purchase_bill_id)
            if bill is None:
                raise NotFoundError(f"Purchase bill {purchase_bill_id} not found.")
            if bill.status_code != "posted":
                raise ValidationError("Only posted purchase bills can be matched to GRNs.")

            bill_line_options: list[GrnBillMatchBillLineDTO] = []
            for bill_line in bill.lines:
                total_qty = self._bill_line_quantity(bill_line)
                existing_links = link_repo.list_bill_links_for_bill_line(company_id, bill_line.id)
                matched_qty = sum((Decimal(str(link.matched_qty)) for link in existing_links), _ZERO)
                available_qty = quantize_quantity(total_qty - matched_qty)
                if available_qty <= _ZERO:
                    continue
                bill_line_options.append(
                    GrnBillMatchBillLineDTO(
                        purchase_bill_line_id=bill_line.id,
                        line_number=bill_line.line_number,
                        description=bill_line.description,
                        item_id=bill_line.item_id,
                        quantity=total_qty,
                        matched_qty=quantize_quantity(matched_qty),
                        available_qty=available_qty,
                        unit_cost=bill_line.unit_cost,
                        line_subtotal_amount=bill_line.line_subtotal_amount,
                    )
                )

            receipt_line_options: list[GrnBillMatchReceiptLineDTO] = []
            purchase_order_id = getattr(bill, "source_order_id", None)
            for doc_line in doc_repo.list_posted_goods_receipt_lines(
                company_id,
                purchase_order_id=purchase_order_id,
            ):
                existing_links = link_repo.list_bill_links_for_document(doc_line.id)
                matched_qty = sum((Decimal(str(link.matched_qty)) for link in existing_links), _ZERO)
                received_qty = self._document_line_quantity(doc_line)
                available_qty = quantize_quantity(received_qty - matched_qty)
                if available_qty <= _ZERO:
                    continue
                unit_cost = Decimal(str(doc_line.unit_cost or _ZERO))
                item = getattr(doc_line, "item", None)
                doc = doc_line.inventory_document
                receipt_line_options.append(
                    GrnBillMatchReceiptLineDTO(
                        inventory_document_line_id=doc_line.id,
                        inventory_document_id=doc.id,
                        document_number=doc.document_number,
                        receipt_date=doc.document_date,
                        item_id=doc_line.item_id,
                        item_code=getattr(item, "item_code", "") or "",
                        item_name=getattr(item, "item_name", "") or "",
                        received_qty=received_qty,
                        matched_qty=quantize_quantity(matched_qty),
                        available_qty=available_qty,
                        unit_cost=unit_cost,
                        available_amount=quantize_amount(available_qty * unit_cost),
                    )
                )

            return GrnBillMatchOptionsDTO(
                purchase_bill_id=bill.id,
                bill_number=bill.bill_number,
                bill_date=bill.bill_date,
                bill_status_code=bill.status_code,
                bill_lines=tuple(bill_line_options),
                receipt_lines=tuple(receipt_line_options),
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

    def _require_positive_quantity(self, value: Decimal, label: str) -> Decimal:
        quantity = quantize_quantity(Decimal(str(value)))
        if quantity <= _ZERO:
            raise ValidationError(f"{label} must be greater than zero.")
        return quantity

    def _available_quantity(
        self,
        *,
        total_quantity: Decimal,
        existing_links: list[PurchaseBillLineReceiptLink],
        pending_quantity: Decimal,
    ) -> Decimal:
        matched = sum((Decimal(str(link.matched_qty)) for link in existing_links), _ZERO)
        return quantize_quantity(total_quantity - matched - pending_quantity)

    def _document_line_quantity(self, doc_line: InventoryDocumentLine) -> Decimal:
        return quantize_quantity(Decimal(str(doc_line.base_quantity or doc_line.quantity or _ZERO)))

    def _bill_line_quantity(self, bill_line: object) -> Decimal:
        return quantize_quantity(
            Decimal(str(getattr(bill_line, "base_quantity", None) or getattr(bill_line, "quantity", None) or _ZERO))
        )

    def _receipt_amount_for_quantity(self, doc_line: InventoryDocumentLine, quantity: Decimal) -> Decimal:
        unit_cost = Decimal(str(doc_line.unit_cost or _ZERO))
        return quantize_amount(quantity * unit_cost)

    def _bill_amount_for_quantity(self, bill_line: object, quantity: Decimal) -> Decimal:
        bill_quantity = self._bill_line_quantity(bill_line)
        if bill_quantity <= _ZERO:
            raise ValidationError(
                f"Bill line {getattr(bill_line, 'line_number', '')} must have a positive quantity to match."
            )
        line_subtotal = Decimal(str(getattr(bill_line, "line_subtotal_amount", _ZERO_AMT) or _ZERO_AMT))
        unit_amount = line_subtotal / bill_quantity
        return quantize_amount(quantity * unit_amount)

    def _resolve_fiscal_period_id(
        self,
        session: Session,
        *,
        company_id: int,
        bill_date: date,
        fiscal_period_id: int | None,
    ) -> int:
        if fiscal_period_id is not None:
            return fiscal_period_id
        if self._fiscal_period_repository_factory is None:
            raise ValidationError("A fiscal period is required to match GRNs to bills.")
        fiscal_period = self._fiscal_period_repository_factory(session).get_covering_date(
            company_id,
            bill_date,
        )
        if fiscal_period is None:
            raise ValidationError("Bill date must fall within an existing fiscal period.")
        if fiscal_period.status_code == "LOCKED":
            raise PeriodLockedError("GRN matching cannot be posted into a locked fiscal period.")
        if fiscal_period.status_code != "OPEN":
            raise ValidationError("GRN matching can only be posted into an open fiscal period.")
        return fiscal_period.id
