from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.app.context.app_context import AppContext
from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.accounting.fiscal_periods.repositories.fiscal_period_repository import (
    FiscalPeriodRepository,
)
from seeker_accounting.modules.accounting.journals.models.journal_entry import JournalEntry
from seeker_accounting.modules.accounting.journals.models.journal_entry_line import JournalEntryLine
from seeker_accounting.modules.accounting.journals.repositories.journal_entry_repository import (
    JournalEntryRepository,
)
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.inventory.dto.inventory_document_dto import InventoryPostingResultDTO
from seeker_accounting.modules.inventory.models.inventory_cost_layer import InventoryCostLayer
from seeker_accounting.modules.inventory.repositories.inventory_cost_layer_repository import (
    InventoryCostLayerRepository,
)
from seeker_accounting.modules.inventory.repositories.inventory_document_repository import (
    InventoryDocumentRepository,
)
from seeker_accounting.modules.inventory.repositories.item_repository import ItemRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, PeriodLockedError, ValidationError
from seeker_accounting.platform.numbering.numbering_service import NumberingService

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
FiscalPeriodRepositoryFactory = Callable[[Session], FiscalPeriodRepository]
JournalEntryRepositoryFactory = Callable[[Session], JournalEntryRepository]
InventoryDocumentRepositoryFactory = Callable[[Session], InventoryDocumentRepository]
ItemRepositoryFactory = Callable[[Session], ItemRepository]
InventoryCostLayerRepositoryFactory = Callable[[Session], InventoryCostLayerRepository]


class InventoryPostingService:
    DOCUMENT_TYPE_CODE = "INVENTORY_DOCUMENT"

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        app_context: AppContext,
        company_repository_factory: CompanyRepositoryFactory,
        fiscal_period_repository_factory: FiscalPeriodRepositoryFactory,
        journal_entry_repository_factory: JournalEntryRepositoryFactory,
        inventory_document_repository_factory: InventoryDocumentRepositoryFactory,
        item_repository_factory: ItemRepositoryFactory,
        inventory_cost_layer_repository_factory: InventoryCostLayerRepositoryFactory,
        numbering_service: NumberingService,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._app_context = app_context
        self._company_repository_factory = company_repository_factory
        self._fiscal_period_repository_factory = fiscal_period_repository_factory
        self._journal_entry_repository_factory = journal_entry_repository_factory
        self._inventory_document_repository_factory = inventory_document_repository_factory
        self._item_repository_factory = item_repository_factory
        self._inventory_cost_layer_repository_factory = inventory_cost_layer_repository_factory
        self._numbering_service = numbering_service
        self._audit_service = audit_service

    def post_inventory_document(
        self,
        company_id: int,
        document_id: int,
        actor_user_id: int | None = None,
    ) -> InventoryPostingResultDTO:
        with self._unit_of_work_factory() as uow:
            actor_id = actor_user_id if actor_user_id is not None else self._app_context.current_user_id
            self._require_company_exists(uow.session, company_id)

            doc_repo = self._inventory_document_repository_factory(uow.session)
            item_repo = self._item_repository_factory(uow.session)
            cost_layer_repo = self._inventory_cost_layer_repository_factory(uow.session)
            journal_repo = self._journal_entry_repository_factory(uow.session)
            fp_repo = self._fiscal_period_repository_factory(uow.session)

            doc = doc_repo.get_detail(company_id, document_id)
            if doc is None:
                raise NotFoundError(f"Inventory document with id {document_id} was not found.")
            if doc.status_code != "draft":
                raise ValidationError("Only draft documents can be posted.")
            if not doc.lines:
                raise ValidationError("Document must have at least one line to be posted.")

            # --- Period validation ---
            fiscal_period = fp_repo.get_covering_date(company_id, doc.document_date)
            if fiscal_period is None:
                raise ValidationError("Document date must fall within an existing fiscal period.")
            if fiscal_period.status_code == "LOCKED":
                raise PeriodLockedError("Document cannot be posted into a locked fiscal period.")
            if fiscal_period.status_code != "OPEN":
                raise ValidationError("Document can only be posted into an open fiscal period.")

            # --- Process lines and build journal entries ---
            journal_lines: list[JournalEntryLine] = []
            line_number = 1

            for doc_line in sorted(doc.lines, key=lambda l: l.line_number):
                item = item_repo.get_by_id(company_id, doc_line.item_id)
                if item is None:
                    raise ValidationError(f"Item with id {doc_line.item_id} was not found.")
                if item.inventory_account_id is None:
                    raise ValidationError(
                        f"Item '{item.item_code}' must have an inventory account configured."
                    )

                inventory_account_id = item.inventory_account_id
                counterparty_account_id = doc_line.counterparty_account_id
                if counterparty_account_id is None:
                    # Fallback: use COGS for issues, expense for adjustments
                    if doc.document_type_code == "issue":
                        counterparty_account_id = item.cogs_account_id or item.expense_account_id
                    else:
                        counterparty_account_id = item.expense_account_id

                if counterparty_account_id is None:
                    raise ValidationError(
                        f"Item '{item.item_code}': counterparty account is required for posting."
                    )

                if doc.document_type_code == "receipt":
                    # Receipt: create cost layer, debit inventory, credit counterparty
                    unit_cost = doc_line.unit_cost
                    if unit_cost is None or unit_cost <= 0:
                        raise ValidationError(
                            f"Item '{item.item_code}': unit cost is required for receipt posting."
                        )
                    stock_qty = doc_line.base_quantity if doc_line.base_quantity is not None else doc_line.quantity
                    # unit_cost is per-transaction-UoM; convert to per-base-UoM cost
                    base_unit_cost = (unit_cost * doc_line.quantity / stock_qty).quantize(Decimal("0.0001")) if stock_qty else unit_cost
                    amount = (stock_qty * base_unit_cost).quantize(Decimal("0.01"))

                    # Create cost layer
                    cost_layer_repo.add(InventoryCostLayer(
                        company_id=company_id,
                        item_id=item.id,
                        inventory_document_line_id=doc_line.id,
                        layer_date=doc.document_date,
                        quantity_in=stock_qty,
                        quantity_remaining=stock_qty,
                        unit_cost=base_unit_cost,
                    ))

                    # Debit inventory
                    journal_lines.append(JournalEntryLine(
                        journal_entry_id=0,
                        line_number=line_number,
                        account_id=inventory_account_id,
                        line_description=f"Receipt: {item.item_code} x {stock_qty}",
                        debit_amount=amount,
                        credit_amount=Decimal("0.00"),
                        contract_id=doc_line.contract_id,
                        project_id=doc_line.project_id,
                        project_job_id=doc_line.project_job_id,
                        project_cost_code_id=doc_line.project_cost_code_id,
                    ))
                    line_number += 1

                    # Credit counterparty
                    journal_lines.append(JournalEntryLine(
                        journal_entry_id=0,
                        line_number=line_number,
                        account_id=counterparty_account_id,
                        line_description=f"Receipt: {item.item_code} counterparty",
                        debit_amount=Decimal("0.00"),
                        credit_amount=amount,
                        contract_id=doc_line.contract_id,
                        project_id=doc_line.project_id,
                        project_job_id=doc_line.project_job_id,
                        project_cost_code_id=doc_line.project_cost_code_id,
                    ))
                    line_number += 1

                    # Update line_amount on the document line
                    doc_line.line_amount = amount

                elif doc.document_type_code == "issue":
                    # Issue: consume from cost layers (weighted average), credit inventory, debit counterparty
                    stock_qty = doc_line.base_quantity if doc_line.base_quantity is not None else doc_line.quantity
                    qty_to_consume = stock_qty
                    amount = self._consume_stock_weighted_average(
                        cost_layer_repo, company_id, item.id, qty_to_consume
                    )

                    # Credit inventory
                    journal_lines.append(JournalEntryLine(
                        journal_entry_id=0,
                        line_number=line_number,
                        account_id=inventory_account_id,
                        line_description=f"Issue: {item.item_code} x {qty_to_consume}",
                        debit_amount=Decimal("0.00"),
                        credit_amount=amount,
                        contract_id=doc_line.contract_id,
                        project_id=doc_line.project_id,
                        project_job_id=doc_line.project_job_id,
                        project_cost_code_id=doc_line.project_cost_code_id,
                    ))
                    line_number += 1

                    # Debit counterparty (COGS/expense)
                    journal_lines.append(JournalEntryLine(
                        journal_entry_id=0,
                        line_number=line_number,
                        account_id=counterparty_account_id,
                        line_description=f"Issue: {item.item_code} counterparty",
                        debit_amount=amount,
                        credit_amount=Decimal("0.00"),
                        contract_id=doc_line.contract_id,
                        project_id=doc_line.project_id,
                        project_job_id=doc_line.project_job_id,
                        project_cost_code_id=doc_line.project_cost_code_id,
                    ))
                    line_number += 1

                    doc_line.unit_cost = (amount / qty_to_consume).quantize(Decimal("0.0001")) if qty_to_consume else Decimal("0")
                    doc_line.line_amount = amount

                elif doc.document_type_code == "adjustment":
                    if doc_line.quantity > 0:
                        # Positive adjustment: debit inventory, credit counterparty
                        unit_cost = doc_line.unit_cost
                        if unit_cost is None or unit_cost <= 0:
                            raise ValidationError(
                                f"Item '{item.item_code}': unit cost is required for positive adjustments."
                            )
                        stock_qty = doc_line.base_quantity if doc_line.base_quantity is not None else doc_line.quantity
                        base_unit_cost = (unit_cost * doc_line.quantity / stock_qty).quantize(Decimal("0.0001")) if stock_qty else unit_cost
                        amount = (stock_qty * base_unit_cost).quantize(Decimal("0.01"))

                        cost_layer_repo.add(InventoryCostLayer(
                            company_id=company_id,
                            item_id=item.id,
                            inventory_document_line_id=doc_line.id,
                            layer_date=doc.document_date,
                            quantity_in=stock_qty,
                            quantity_remaining=stock_qty,
                            unit_cost=base_unit_cost,
                        ))

                        journal_lines.append(JournalEntryLine(
                            journal_entry_id=0,
                            line_number=line_number,
                            account_id=inventory_account_id,
                            line_description=f"Adjustment(+): {item.item_code} x {stock_qty}",
                            debit_amount=amount,
                            credit_amount=Decimal("0.00"),
                            contract_id=doc_line.contract_id,
                            project_id=doc_line.project_id,
                            project_job_id=doc_line.project_job_id,
                            project_cost_code_id=doc_line.project_cost_code_id,
                        ))
                        line_number += 1
                        journal_lines.append(JournalEntryLine(
                            journal_entry_id=0,
                            line_number=line_number,
                            account_id=counterparty_account_id,
                            line_description=f"Adjustment(+): {item.item_code} counterparty",
                            debit_amount=Decimal("0.00"),
                            credit_amount=amount,
                            contract_id=doc_line.contract_id,
                            project_id=doc_line.project_id,
                            project_job_id=doc_line.project_job_id,
                            project_cost_code_id=doc_line.project_cost_code_id,
                        ))
                        line_number += 1
                        doc_line.line_amount = amount

                    else:
                        # Negative adjustment: credit inventory, debit counterparty
                        stock_qty = doc_line.base_quantity if doc_line.base_quantity is not None else doc_line.quantity
                        qty_to_consume = abs(stock_qty)
                        amount = self._consume_stock_weighted_average(
                            cost_layer_repo, company_id, item.id, qty_to_consume
                        )

                        journal_lines.append(JournalEntryLine(
                            journal_entry_id=0,
                            line_number=line_number,
                            account_id=inventory_account_id,
                            line_description=f"Adjustment(-): {item.item_code} x {qty_to_consume}",
                            debit_amount=Decimal("0.00"),
                            credit_amount=amount,
                            contract_id=doc_line.contract_id,
                            project_id=doc_line.project_id,
                            project_job_id=doc_line.project_job_id,
                            project_cost_code_id=doc_line.project_cost_code_id,
                        ))
                        line_number += 1
                        journal_lines.append(JournalEntryLine(
                            journal_entry_id=0,
                            line_number=line_number,
                            account_id=counterparty_account_id,
                            line_description=f"Adjustment(-): {item.item_code} counterparty",
                            debit_amount=amount,
                            credit_amount=Decimal("0.00"),
                            contract_id=doc_line.contract_id,
                            project_id=doc_line.project_id,
                            project_job_id=doc_line.project_job_id,
                            project_cost_code_id=doc_line.project_cost_code_id,
                        ))
                        line_number += 1
                        doc_line.line_amount = amount

            # --- Recalculate total value ---
            doc.total_value = sum(
                abs(line.line_amount) for line in doc.lines if line.line_amount is not None
            )

            # --- Create journal entry ---
            journal_entry = JournalEntry(
                company_id=company_id,
                fiscal_period_id=fiscal_period.id,
                entry_number=None,
                entry_date=doc.document_date,
                journal_type_code="INVENTORY",
                reference_text=doc.document_number,
                description=f"Inventory {doc.document_type_code} {doc.document_number}",
                source_module_code="inventory",
                source_document_type="inventory_document",
                source_document_id=doc.id,
                status_code="POSTED",
                posted_at=datetime.utcnow(),
                posted_by_user_id=actor_id,
                created_by_user_id=actor_id,
            )
            journal_repo.add(journal_entry)
            uow.session.flush()

            journal_entry.entry_number = self._numbering_service.issue_next_number(
                uow.session, company_id=company_id, document_type_code="JOURNAL_ENTRY"
            )
            journal_repo.save(journal_entry)

            for jl in journal_lines:
                jl.journal_entry_id = journal_entry.id
            uow.session.add_all(journal_lines)

            # --- Update document status and numbering ---
            doc.document_number = self._numbering_service.issue_next_number(
                uow.session, company_id=company_id, document_type_code=self.DOCUMENT_TYPE_CODE
            )
            doc.status_code = "posted"
            doc.posted_journal_entry_id = journal_entry.id
            doc.posted_at = datetime.utcnow()
            doc.posted_by_user_id = actor_id
            doc_repo.save(doc)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_posting_integrity_error(exc) from exc

            from seeker_accounting.modules.audit.event_type_catalog import INVENTORY_DOCUMENT_POSTED
            self._record_audit(company_id, INVENTORY_DOCUMENT_POSTED, "InventoryDocument", doc.id, "Posted inventory document")
            return InventoryPostingResultDTO(
                company_id=company_id,
                document_id=doc.id,
                document_number=doc.document_number,
                journal_entry_id=journal_entry.id,
                journal_entry_number=journal_entry.entry_number or "",
                posted_at=doc.posted_at or datetime.utcnow(),
                posted_by_user_id=doc.posted_by_user_id,
            )

    # ------------------------------------------------------------------
    # Weighted average stock consumption
    # ------------------------------------------------------------------

    def _consume_stock_weighted_average(
        self,
        cost_layer_repo: InventoryCostLayerRepository,
        company_id: int,
        item_id: int,
        quantity: Decimal,
    ) -> Decimal:
        """Consume stock using weighted average cost. Returns total consumed value."""
        on_hand = cost_layer_repo.get_stock_on_hand(company_id, item_id)
        if quantity > on_hand:
            raise ValidationError(
                f"Insufficient stock. On hand: {on_hand}, requested: {quantity}."
            )

        avg_cost = cost_layer_repo.get_weighted_average_cost(company_id, item_id)
        if avg_cost is None:
            raise ValidationError("Cannot determine weighted average cost — no stock layers found.")

        total_value = (quantity * avg_cost).quantize(Decimal("0.01"))

        # Consume from layers (oldest first for deduction tracking)
        layers = cost_layer_repo.list_for_item(company_id, item_id, with_remaining_only=True)
        remaining_to_consume = quantity
        for layer in layers:
            if remaining_to_consume <= 0:
                break
            consumed = min(remaining_to_consume, layer.quantity_remaining)
            layer.quantity_remaining -= consumed
            cost_layer_repo.save(layer)
            remaining_to_consume -= consumed

        return total_value

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _require_company_exists(self, session: Session | None, company_id: int) -> None:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        repo = self._company_repository_factory(session)
        if repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

    def _translate_posting_integrity_error(self, exc: IntegrityError) -> ValidationError | ConflictError:
        msg = str(exc.orig).lower() if exc.orig is not None else str(exc).lower()
        if "unique" in msg and "document_number" in msg:
            return ConflictError("An inventory document with this number already exists.")
        if "unique" in msg and "entry_number" in msg:
            return ConflictError("Journal entry numbering conflicts with an existing posted entry.")
        return ValidationError("Inventory document could not be posted.")

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
            pass  # Audit must not break business operations
