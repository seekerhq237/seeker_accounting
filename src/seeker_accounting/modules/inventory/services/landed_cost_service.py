"""Landed Cost Service — P5 / Slice 6.2.

Creates and posts landed-cost vouchers that allocate import charges (freight,
duty, insurance, other) across linked GRN inventory documents.

Posting creates:
  - Stock ledger revaluation entries (direction +1 for each line, at the
    allocated cost delta)
  - Journal entry: Dr Inventory (per item)  Cr Suspense/AP (allocable account)

allocation_basis_code:
  'by_value'   — weight proportional to line value
  'by_qty'     — weight proportional to base qty
  'by_weight'  — weight proportional to allocation_weight set by user
  'manual'     — use pre-set allocated_amount on each receipt
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Callable

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
from seeker_accounting.modules.inventory.models.inventory_document_line import InventoryDocumentLine
from seeker_accounting.modules.inventory.models.landed_cost_voucher import (
    LandedCostVoucher,
    LandedCostVoucherReceipt,
)
from seeker_accounting.modules.inventory.repositories.inventory_document_repository import (
    InventoryDocumentRepository,
)
from seeker_accounting.modules.inventory.repositories.landed_cost_voucher_repository import (
    LandedCostVoucherRepository,
)
from seeker_accounting.modules.inventory.services.stock_ledger_service import StockLedgerService
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError
from seeker_accounting.platform.numerics.rounding_policy import (
    quantize_amount,
    quantize_internal_cost,
    quantize_quantity,
)

_ZERO = Decimal("0")
_ZERO_AMT = Decimal("0.00")

JournalEntryRepositoryFactory = Callable[[Session], JournalEntryRepository]
AccountRoleMappingRepositoryFactory = Callable[[Session], AccountRoleMappingRepository]
LandedCostVoucherRepositoryFactory = Callable[[Session], LandedCostVoucherRepository]
InventoryDocumentRepositoryFactory = Callable[[Session], InventoryDocumentRepository]


@dataclass
class LandedCostReceiptLineCommand:
    inventory_document_id: int
    allocation_weight: Decimal | None = None  # for 'by_weight' / 'manual'


@dataclass
class CreateLandedCostCommand:
    company_id: int
    voucher_date: date
    declaration_number: str | None
    total_freight: Decimal
    total_duty: Decimal
    total_insurance: Decimal
    total_other: Decimal
    allocation_basis_code: str
    notes: str | None
    receipt_lines: list[LandedCostReceiptLineCommand]


class LandedCostService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        stock_ledger_service: StockLedgerService,
        journal_entry_repository_factory: JournalEntryRepositoryFactory,
        account_role_mapping_repository_factory: AccountRoleMappingRepositoryFactory,
        landed_cost_voucher_repository_factory: LandedCostVoucherRepositoryFactory,
        inventory_document_repository_factory: InventoryDocumentRepositoryFactory,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._stock_ledger_service = stock_ledger_service
        self._je_repo_factory = journal_entry_repository_factory
        self._role_mapping_factory = account_role_mapping_repository_factory
        self._lcv_repo_factory = landed_cost_voucher_repository_factory
        self._doc_repo_factory = inventory_document_repository_factory

    # ------------------------------------------------------------------
    # Create draft voucher
    # ------------------------------------------------------------------

    def create(self, cmd: CreateLandedCostCommand) -> int:
        if not cmd.receipt_lines:
            raise ValidationError("At least one GRN receipt must be linked.")
        total_cost = (
            cmd.total_freight + cmd.total_duty + cmd.total_insurance + cmd.total_other
        )
        if total_cost <= _ZERO:
            raise ValidationError("Total landed cost must be positive.")

        with self._uow_factory() as uow:
            lcv_repo = self._lcv_repo_factory(uow.session)

            voucher_number = self._generate_number(uow.session, cmd.company_id)
            voucher = LandedCostVoucher(
                company_id=cmd.company_id,
                voucher_number=voucher_number,
                voucher_date=cmd.voucher_date,
                declaration_number=cmd.declaration_number,
                total_freight=cmd.total_freight,
                total_duty=cmd.total_duty,
                total_insurance=cmd.total_insurance,
                total_other=cmd.total_other,
                allocation_basis_code=cmd.allocation_basis_code,
                status_code="draft",
                notes=cmd.notes,
            )
            lcv_repo.add(voucher)
            uow.session.flush()

            for rl in cmd.receipt_lines:
                receipt = LandedCostVoucherReceipt(
                    voucher_id=voucher.id,
                    inventory_document_id=rl.inventory_document_id,
                    allocation_weight=rl.allocation_weight,
                )
                lcv_repo.add_receipt(receipt)

            uow.commit()
            return voucher.id

    # ------------------------------------------------------------------
    # Post voucher
    # ------------------------------------------------------------------

    def post(
        self,
        company_id: int,
        voucher_id: int,
        fiscal_period_id: int,
        landed_cost_account_id: int,
        actor_user_id: int | None = None,
    ) -> int:
        """Post the voucher: allocate costs, revalue stock, create JE."""
        with self._uow_factory() as uow:
            lcv_repo = self._lcv_repo_factory(uow.session)
            doc_repo = self._doc_repo_factory(uow.session)

            voucher = lcv_repo.get(voucher_id)
            if voucher is None or voucher.company_id != company_id:
                raise NotFoundError(f"Landed cost voucher {voucher_id} not found.")
            if voucher.status_code != "draft":
                raise ConflictError("Only draft vouchers can be posted.")

            receipts = lcv_repo.list_receipts(voucher_id)
            if not receipts:
                raise ValidationError("No receipts attached to voucher.")

            total_cost = voucher.total_landed_cost

            # Compute allocation weights per GRN
            allocation_map = self._compute_allocations(
                uow.session, voucher, receipts, total_cost, doc_repo
            )

            je_lines: list[JournalEntryLine] = []
            line_num = 1
            total_allocated = _ZERO_AMT

            for receipt in receipts:
                allocated = allocation_map.get(receipt.id, _ZERO_AMT)
                receipt.allocated_amount = allocated
                total_allocated += allocated

                if allocated <= _ZERO:
                    continue

                doc = doc_repo.get(receipt.inventory_document_id)
                if doc is None:
                    continue

                for doc_line in doc.lines:
                    line_share = self._prorate_to_line(doc_line, allocated, doc.lines)
                    if line_share <= _ZERO:
                        continue

                    qty = quantize_quantity(doc_line.base_quantity or doc_line.quantity)
                    if qty <= _ZERO:
                        continue
                    cost_delta = quantize_internal_cost(line_share / qty)

                    self._stock_ledger_service.append(
                        uow.session,
                        company_id=company_id,
                        item_id=doc_line.item_id,
                        location_id=doc.location_id,
                        posting_date=voucher.voucher_date,
                        document_type_code="landed_cost_revaluation",
                        inventory_document_line_id=doc_line.id,
                        direction=1,
                        quantity_base=qty,
                        unit_cost=cost_delta,
                    )

                    from seeker_accounting.modules.inventory.repositories.item_repository import ItemRepository
                    item = ItemRepository(uow.session).get(doc_line.item_id)
                    if item and item.inventory_account_id:
                        je_lines.append(
                            JournalEntryLine(
                                journal_entry_id=0,
                                line_number=line_num,
                                account_id=item.inventory_account_id,
                                line_description=f"Landed cost – {item.item_name}",
                                debit_amount=quantize_amount(line_share),
                                credit_amount=_ZERO_AMT,
                            )
                        )
                        line_num += 1

            # Cr Landed cost liability / AP
            je_lines.append(
                JournalEntryLine(
                    journal_entry_id=0,
                    line_number=line_num,
                    account_id=landed_cost_account_id,
                    line_description=f"Landed cost payable – {voucher.voucher_number}",
                    debit_amount=_ZERO_AMT,
                    credit_amount=quantize_amount(total_allocated),
                )
            )

            je_repo = self._je_repo_factory(uow.session)
            journal_entry = JournalEntry(
                company_id=company_id,
                fiscal_period_id=fiscal_period_id,
                entry_number=None,
                entry_date=voucher.voucher_date,
                journal_type_code="INVENTORY",
                reference_text=voucher.voucher_number,
                description=f"Landed cost {voucher.voucher_number}",
                source_module_code="inventory",
                source_document_type="landed_cost_voucher",
                source_document_id=voucher.id,
                status_code="POSTED",
                posted_at=datetime.utcnow(),
                posted_by_user_id=actor_user_id,
                created_by_user_id=actor_user_id,
            )
            je_repo.add(journal_entry)
            uow.session.flush()

            for jl in je_lines:
                jl.journal_entry_id = journal_entry.id
            uow.session.add_all(je_lines)

            voucher.status_code = "posted"
            voucher.posted_journal_entry_id = journal_entry.id
            voucher.posted_at = datetime.utcnow()
            voucher.posted_by_user_id = actor_user_id

            uow.commit()
            return journal_entry.id

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _compute_allocations(
        self,
        session: Session,
        voucher: LandedCostVoucher,
        receipts: list[LandedCostVoucherReceipt],
        total_cost: Decimal,
        doc_repo: InventoryDocumentRepository,
    ) -> dict[int, Decimal]:
        basis = voucher.allocation_basis_code

        if basis == "manual":
            return {r.id: (r.allocated_amount or _ZERO_AMT) for r in receipts}

        weights: dict[int, Decimal] = {}
        for receipt in receipts:
            if basis == "by_weight":
                weights[receipt.id] = receipt.allocation_weight or _ZERO
            elif basis in ("by_value", "by_qty"):
                doc = doc_repo.get(receipt.inventory_document_id)
                if doc is None:
                    weights[receipt.id] = _ZERO
                    continue
                w = _ZERO
                for line in doc.lines:
                    if basis == "by_value":
                        w += line.line_amount or _ZERO
                    else:
                        w += quantize_quantity(line.base_quantity or line.quantity)
                weights[receipt.id] = w
            else:
                weights[receipt.id] = Decimal("1")

        total_weight = sum(weights.values(), _ZERO)
        if total_weight <= _ZERO:
            # Uniform allocation as fallback
            per = quantize_amount(total_cost / len(receipts)) if receipts else _ZERO_AMT
            return {r.id: per for r in receipts}

        return {
            receipt_id: quantize_amount(total_cost * (w / total_weight))
            for receipt_id, w in weights.items()
        }

    def _prorate_to_line(
        self, target_line: InventoryDocumentLine, receipt_total: Decimal, all_lines: list
    ) -> Decimal:
        """Split the receipt allocation across document lines by value."""
        total_val = sum((l.line_amount or _ZERO for l in all_lines), _ZERO)
        if total_val <= _ZERO:
            n = len(all_lines)
            return quantize_amount(receipt_total / n) if n else _ZERO_AMT
        line_val = target_line.line_amount or _ZERO
        return quantize_amount(receipt_total * (line_val / total_val))

    def _generate_number(self, session: Session, company_id: int) -> str:
        from sqlalchemy import func, select
        from seeker_accounting.modules.inventory.models.landed_cost_voucher import LandedCostVoucher as LCV
        count = session.scalar(
            select(func.count(LCV.id)).where(LCV.company_id == company_id)
        ) or 0
        return f"LCV-{company_id:04d}-{count + 1:05d}"
