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
from seeker_accounting.modules.budgeting.services.budget_control_service import BudgetControlService
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.companies.repositories.company_preference_repository import (
    CompanyPreferenceRepository,
)
from seeker_accounting.modules.inventory.dto.inventory_document_commands import ReverseInventoryDocumentCommand
from seeker_accounting.modules.inventory.dto.inventory_document_dto import (
    InventoryPostingResultDTO,
    InventoryReversalResultDTO,
)
from seeker_accounting.modules.inventory.models.cost_layer_consumption import CostLayerConsumption
from seeker_accounting.modules.inventory.models.inventory_cost_layer import InventoryCostLayer
from seeker_accounting.modules.inventory.models.inventory_document import InventoryDocument
from seeker_accounting.modules.inventory.models.inventory_document_line import InventoryDocumentLine
from seeker_accounting.modules.inventory.models.inventory_document_line_serial import (
    InventoryDocumentLineSerial,
)
from seeker_accounting.modules.inventory.models.item_serial import ItemSerial
from seeker_accounting.modules.inventory.repositories.inventory_cost_layer_repository import (
    InventoryCostLayerRepository,
)
from seeker_accounting.modules.inventory.repositories.inventory_document_repository import (
    InventoryDocumentRepository,
)
from seeker_accounting.modules.inventory.repositories.item_repository import ItemRepository
from seeker_accounting.modules.inventory.services.inventory_document_service import (
    _DOC_TYPE_ACTION,
    _LEGACY_DOCUMENT_TYPES,
)
from seeker_accounting.modules.inventory.repositories.cost_layer_consumption_repository import (
    CostLayerConsumptionRepository,
)
from seeker_accounting.modules.inventory.services.costing_strategies import CostingStrategyRouter
from seeker_accounting.modules.inventory.services.stock_ledger_service import StockLedgerService
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, PeriodLockedError, ValidationError
from seeker_accounting.platform.numbering.numbering_service import NumberingService

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
CompanyPreferenceRepositoryFactory = Callable[[Session], CompanyPreferenceRepository]
FiscalPeriodRepositoryFactory = Callable[[Session], FiscalPeriodRepository]
JournalEntryRepositoryFactory = Callable[[Session], JournalEntryRepository]
InventoryDocumentRepositoryFactory = Callable[[Session], InventoryDocumentRepository]
ItemRepositoryFactory = Callable[[Session], ItemRepository]
InventoryCostLayerRepositoryFactory = Callable[[Session], InventoryCostLayerRepository]
CostLayerConsumptionRepositoryFactory = Callable[[Session], CostLayerConsumptionRepository]


class _NoOpConsumptionRepo:
    """Fallback used when no consumption-repo factory is configured.

    Silently drops ``add`` calls so that the posting service degrades
    gracefully in test contexts that don't provide the full factory wiring.
    """

    def add(self, _consumption: object) -> None:  # noqa: D401
        pass


class InventoryPostingService:
    DOCUMENT_TYPE_CODE = "INVENTORY_DOCUMENT"

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        app_context: AppContext,
        company_repository_factory: CompanyRepositoryFactory,
        company_preference_repository_factory: CompanyPreferenceRepositoryFactory | None,
        fiscal_period_repository_factory: FiscalPeriodRepositoryFactory,
        journal_entry_repository_factory: JournalEntryRepositoryFactory,
        inventory_document_repository_factory: InventoryDocumentRepositoryFactory,
        item_repository_factory: ItemRepositoryFactory,
        inventory_cost_layer_repository_factory: InventoryCostLayerRepositoryFactory,
        numbering_service: NumberingService,
        stock_ledger_service: StockLedgerService,
        cost_layer_consumption_repository_factory: CostLayerConsumptionRepositoryFactory | None = None,
        permission_service: PermissionService | None = None,
        budget_control_service: BudgetControlService | None = None,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._app_context = app_context
        self._company_repository_factory = company_repository_factory
        self._company_preference_repository_factory = company_preference_repository_factory
        self._fiscal_period_repository_factory = fiscal_period_repository_factory
        self._journal_entry_repository_factory = journal_entry_repository_factory
        self._inventory_document_repository_factory = inventory_document_repository_factory
        self._item_repository_factory = item_repository_factory
        self._inventory_cost_layer_repository_factory = inventory_cost_layer_repository_factory
        self._numbering_service = numbering_service
        self._stock_ledger_service = stock_ledger_service
        self._cost_layer_consumption_repository_factory = cost_layer_consumption_repository_factory
        self._permission_service = permission_service
        self._budget_control_service = budget_control_service
        self._audit_service = audit_service

    def post_inventory_document(
        self,
        company_id: int,
        document_id: int,
        actor_user_id: int | None = None,
    ) -> InventoryPostingResultDTO:
        self._require_permission("inventory.documents.post")
        with self._unit_of_work_factory() as uow:
            actor_id = actor_user_id if actor_user_id is not None else self._app_context.current_user_id
            self._require_company_exists(uow.session, company_id)

            doc_repo = self._inventory_document_repository_factory(uow.session)
            item_repo = self._item_repository_factory(uow.session)
            cost_layer_repo = self._inventory_cost_layer_repository_factory(uow.session)
            journal_repo = self._journal_entry_repository_factory(uow.session)
            fp_repo = self._fiscal_period_repository_factory(uow.session)
            consumption_repo = (
                self._cost_layer_consumption_repository_factory(uow.session)
                if self._cost_layer_consumption_repository_factory is not None
                else _NoOpConsumptionRepo()
            )

            doc = doc_repo.get_detail(company_id, document_id)
            if doc is None:
                raise NotFoundError(f"Inventory document with id {document_id} was not found.")
            if doc.status_code not in {"draft", "pending_posting"}:
                raise ValidationError("Only draft or pending-posting documents can be posted.")
            if not doc.lines:
                raise ValidationError("Document must have at least one line to be posted.")
            if self._inventory_sod_is_enforced(uow.session, company_id):
                if doc.status_code != "pending_posting":
                    raise ValidationError("Document must be submitted before posting.")
                if doc.submitted_by_user_id is not None and doc.submitted_by_user_id == actor_id:
                    raise ValidationError("The submitter cannot also post this inventory document.")

            # --- Period validation ---
            fiscal_period = fp_repo.get_covering_date(company_id, doc.document_date)
            if fiscal_period is None:
                raise ValidationError("Document date must fall within an existing fiscal period.")
            if fiscal_period.status_code == "LOCKED":
                raise PeriodLockedError("Document cannot be posted into a locked fiscal period.")
            if fiscal_period.status_code != "OPEN":
                raise ValidationError("Document can only be posted into an open fiscal period.")

            # --- Process lines and build journal entries ---
            doc_type_action = self._resolve_doc_type_action(doc.document_type_code)
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
                    if doc_type_action == "issue":
                        counterparty_account_id = item.cogs_account_id or item.expense_account_id
                    else:
                        counterparty_account_id = item.expense_account_id

                if counterparty_account_id is None:
                    raise ValidationError(
                        f"Item '{item.item_code}': counterparty account is required for posting."
                    )

                if doc_type_action == "receipt":
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

                    # Create cost layer (now location-aware per Slice 2.2)
                    cost_layer_repo.add(InventoryCostLayer(
                        company_id=company_id,
                        item_id=item.id,
                        location_id=doc.location_id,
                        batch_id=doc_line.batch_id,
                        inventory_document_line_id=doc_line.id,
                        layer_date=doc.document_date,
                        quantity_in=stock_qty,
                        quantity_remaining=stock_qty,
                        unit_cost=base_unit_cost,
                    ))

                    # Append to immutable stock ledger (Slice 2.1 — single writer).
                    self._stock_ledger_service.append(
                        uow.session,
                        company_id=company_id,
                        item_id=item.id,
                        location_id=doc.location_id,
                        posting_date=doc.document_date,
                        document_type_code=doc.document_type_code,
                        inventory_document_line_id=doc_line.id,
                        direction=1,
                        quantity_base=stock_qty,
                        unit_cost=base_unit_cost,
                        batch_id=doc_line.batch_id,
                    )
                    self._mark_serials_for_receipt(uow.session, doc_line, doc.location_id)

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

                elif doc_type_action == "issue":
                    # Issue: consume from cost layers, credit inventory, debit counterparty
                    stock_qty = doc_line.base_quantity if doc_line.base_quantity is not None else doc_line.quantity
                    qty_to_consume = stock_qty
                    amount, _ppv = CostingStrategyRouter.consume_for_issue(
                        costing_method_code=getattr(item, "inventory_cost_method_code", None) or "weighted_average",
                        standard_cost=getattr(item, "standard_cost", None),
                        cost_layer_repo=cost_layer_repo,
                        consumption_repo=consumption_repo,
                        company_id=company_id,
                        item_id=item.id,
                        location_id=doc.location_id,
                        batch_id=doc_line.batch_id,
                        quantity=qty_to_consume,
                        doc_line_id=doc_line.id,
                        posting_date=doc.document_date,
                    )
                    self._enforce_budget_for_issue(doc, doc_line, amount)

                    # Append to immutable stock ledger (Slice 2.1).
                    self._stock_ledger_service.append(
                        uow.session,
                        company_id=company_id,
                        item_id=item.id,
                        location_id=doc.location_id,
                        posting_date=doc.document_date,
                        document_type_code=doc.document_type_code,
                        inventory_document_line_id=doc_line.id,
                        direction=-1,
                        quantity_base=qty_to_consume,
                        unit_cost=(amount / qty_to_consume) if qty_to_consume else Decimal("0"),
                        batch_id=doc_line.batch_id,
                    )
                    self._mark_serials_for_issue(uow.session, doc_line, doc.document_type_code)

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

                elif doc_type_action == "adjustment":
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
                            location_id=doc.location_id,
                            batch_id=doc_line.batch_id,
                            inventory_document_line_id=doc_line.id,
                            layer_date=doc.document_date,
                            quantity_in=stock_qty,
                            quantity_remaining=stock_qty,
                            unit_cost=base_unit_cost,
                        ))

                        # Append to immutable stock ledger (Slice 2.1).
                        self._stock_ledger_service.append(
                            uow.session,
                            company_id=company_id,
                            item_id=item.id,
                            location_id=doc.location_id,
                            posting_date=doc.document_date,
                            document_type_code=doc.document_type_code,
                            inventory_document_line_id=doc_line.id,
                            direction=1,
                            quantity_base=stock_qty,
                            unit_cost=base_unit_cost,
                            batch_id=doc_line.batch_id,
                        )
                        self._mark_serials_for_receipt(uow.session, doc_line, doc.location_id)

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
                        amount, _ppv = CostingStrategyRouter.consume_for_issue(
                            costing_method_code=getattr(item, "inventory_cost_method_code", None) or "weighted_average",
                            standard_cost=getattr(item, "standard_cost", None),
                            cost_layer_repo=cost_layer_repo,
                            consumption_repo=consumption_repo,
                            company_id=company_id,
                            item_id=item.id,
                            location_id=doc.location_id,
                            batch_id=doc_line.batch_id,
                            quantity=qty_to_consume,
                            doc_line_id=doc_line.id,
                            posting_date=doc.document_date,
                        )

                        # Append to immutable stock ledger (Slice 2.1).
                        self._stock_ledger_service.append(
                            uow.session,
                            company_id=company_id,
                            item_id=item.id,
                            location_id=doc.location_id,
                            posting_date=doc.document_date,
                            document_type_code=doc.document_type_code,
                            inventory_document_line_id=doc_line.id,
                            direction=-1,
                            quantity_base=qty_to_consume,
                            unit_cost=(amount / qty_to_consume) if qty_to_consume else Decimal("0"),
                            batch_id=doc_line.batch_id,
                        )
                        self._mark_serials_for_issue(uow.session, doc_line, doc.document_type_code)

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

            # --- Total value is derived from line amounts via the
            # ``InventoryDocument.total_value`` property; no header column to
            # update (Slice 1.2 dropped the denormalised stored total). ---

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
            doc.approved_at = datetime.utcnow()
            doc.approved_by_user_id = actor_id
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

    def reverse_inventory_document(
        self,
        company_id: int,
        document_id: int,
        command: ReverseInventoryDocumentCommand,
    ) -> InventoryReversalResultDTO:
        self._require_permission("inventory.documents.reverse")
        with self._unit_of_work_factory() as uow:
            actor_id = command.reversed_by_user_id if command.reversed_by_user_id is not None else self._app_context.current_user_id
            self._require_company_exists(uow.session, company_id)

            doc_repo = self._inventory_document_repository_factory(uow.session)
            cost_layer_repo = self._inventory_cost_layer_repository_factory(uow.session)
            journal_repo = self._journal_entry_repository_factory(uow.session)
            fp_repo = self._fiscal_period_repository_factory(uow.session)
            consumption_repo = (
                self._cost_layer_consumption_repository_factory(uow.session)
                if self._cost_layer_consumption_repository_factory is not None
                else _NoOpConsumptionRepo()
            )

            original_doc = doc_repo.get_detail(company_id, document_id)
            if original_doc is None:
                raise NotFoundError(f"Inventory document with id {document_id} was not found.")
            if original_doc.status_code != "posted":
                raise ValidationError("Only posted inventory documents can be reversed.")
            if original_doc.reversal_document_id is not None or original_doc.reversed_at is not None:
                raise ValidationError("Inventory document has already been reversed.")
            if original_doc.reversal_of_document_id is not None:
                raise ValidationError("A reversal document cannot be reversed through this workflow.")
            if original_doc.posted_journal_entry_id is None:
                raise ValidationError("Posted inventory document is missing its journal entry link.")

            fiscal_period = fp_repo.get_covering_date(company_id, command.reverse_date)
            if fiscal_period is None:
                raise ValidationError("Reversal date must fall within an existing fiscal period.")
            if fiscal_period.status_code == "LOCKED":
                raise PeriodLockedError("Inventory document cannot be reversed into a locked fiscal period.")
            if fiscal_period.status_code != "OPEN":
                raise ValidationError("Inventory document can only be reversed into an open fiscal period.")

            original_journal = journal_repo.get_detail(company_id, original_doc.posted_journal_entry_id)
            if original_journal is None or not original_journal.lines:
                raise ValidationError("Original journal entry could not be loaded for reversal.")

            reversed_at = datetime.utcnow()
            reversal_doc = InventoryDocument(
                company_id=company_id,
                document_number=self._numbering_service.issue_next_number(
                    uow.session, company_id=company_id, document_type_code=self.DOCUMENT_TYPE_CODE
                ),
                document_type_code=original_doc.document_type_code,
                document_date=command.reverse_date,
                status_code="posted",
                location_id=original_doc.location_id,
                reason_code_id=original_doc.reason_code_id,
                reference_number=f"REV-{original_doc.document_number}",
                notes=f"Reversal of inventory document {original_doc.document_number}",
                source_module_code="inventory",
                source_document_type="inventory_document_reversal",
                source_document_id=original_doc.id,
                reversal_of_document_id=original_doc.id,
                reverse_reason_code_id=command.reason_code_id,
                posted_at=reversed_at,
                posted_by_user_id=actor_id,
                approved_at=reversed_at,
                approved_by_user_id=actor_id,
                contract_id=original_doc.contract_id,
                project_id=original_doc.project_id,
                stock_count_session_id=original_doc.stock_count_session_id,
                bom_id=original_doc.bom_id,
                production_order_id=original_doc.production_order_id,
            )
            for original_line in sorted(original_doc.lines, key=lambda line: line.line_number):
                reversal_doc.lines.append(
                    InventoryDocumentLine(
                        line_number=original_line.line_number,
                        item_id=original_line.item_id,
                        batch_id=original_line.batch_id,
                        quantity=-original_line.quantity,
                        unit_cost=original_line.unit_cost,
                        line_amount=-(original_line.line_amount or Decimal("0.00")),
                        counterparty_account_id=original_line.counterparty_account_id,
                        line_description=f"Reversal of line {original_line.line_number}",
                        transaction_uom_id=original_line.transaction_uom_id,
                        uom_ratio_snapshot=original_line.uom_ratio_snapshot,
                        base_quantity=-(original_line.base_quantity if original_line.base_quantity is not None else original_line.quantity),
                        contract_id=original_line.contract_id,
                        project_id=original_line.project_id,
                        project_job_id=original_line.project_job_id,
                        project_cost_code_id=original_line.project_cost_code_id,
                        serial_links=[
                            InventoryDocumentLineSerial(serial_id=link.serial_id)
                            for link in original_line.serial_links
                        ],
                    )
                )
            doc_repo.add(reversal_doc)
            uow.session.flush()

            for original_line, reversal_line in zip(
                sorted(original_doc.lines, key=lambda line: line.line_number),
                sorted(reversal_doc.lines, key=lambda line: line.line_number),
                strict=True,
            ):
                original_direction, quantity_base = self._document_line_direction_and_quantity(original_doc, original_line)
                reversal_direction = -original_direction
                line_amount = abs(original_line.line_amount or Decimal("0.00"))
                unit_cost = (line_amount / quantity_base).quantize(Decimal("0.0001")) if quantity_base else Decimal("0.0000")
                if reversal_direction < 0:
                    source_layer = cost_layer_repo.get_by_document_line_id(original_line.id)
                    if source_layer is None:
                        raise ValidationError("Original receipt cost layer could not be found for reversal.")
                    if source_layer.quantity_remaining < quantity_base:
                        raise ValidationError("Original receipt cost layer has already been consumed and cannot be reversed safely.")
                    source_layer.quantity_remaining -= quantity_base
                    cost_layer_repo.save(source_layer)
                    consumption_repo.add(
                        CostLayerConsumption(
                            source_layer_id=source_layer.id,
                            consuming_doc_line_id=reversal_line.id,
                            consumed_quantity=quantity_base,
                            consumed_value=line_amount,
                            posting_date=command.reverse_date,
                        )
                    )
                else:
                    cost_layer_repo.add(
                        InventoryCostLayer(
                            company_id=company_id,
                            item_id=reversal_line.item_id,
                            location_id=reversal_doc.location_id,
                            batch_id=reversal_line.batch_id,
                            inventory_document_line_id=reversal_line.id,
                            layer_date=command.reverse_date,
                            quantity_in=quantity_base,
                            quantity_remaining=quantity_base,
                            unit_cost=unit_cost,
                        )
                    )

                self._stock_ledger_service.append(
                    uow.session,
                    company_id=company_id,
                    item_id=reversal_line.item_id,
                    location_id=reversal_doc.location_id,
                    posting_date=command.reverse_date,
                    document_type_code=reversal_doc.document_type_code,
                    inventory_document_line_id=reversal_line.id,
                    direction=reversal_direction,
                    quantity_base=quantity_base,
                    unit_cost=unit_cost,
                    batch_id=reversal_line.batch_id,
                )
                self._mark_serials_for_reversal(uow.session, reversal_line, reversal_direction, reversal_doc.location_id)

            reversing_journal = JournalEntry(
                company_id=company_id,
                fiscal_period_id=fiscal_period.id,
                entry_number=None,
                entry_date=command.reverse_date,
                journal_type_code="INVENTORY",
                reference_text=reversal_doc.document_number,
                description=f"Reversal of inventory document {original_doc.document_number}",
                source_module_code="inventory",
                source_document_type="inventory_document_reversal",
                source_document_id=reversal_doc.id,
                status_code="POSTED",
                posted_at=reversed_at,
                posted_by_user_id=actor_id,
                created_by_user_id=actor_id,
            )
            journal_repo.add(reversing_journal)
            uow.session.flush()
            reversing_journal.entry_number = self._numbering_service.issue_next_number(
                uow.session, company_id=company_id, document_type_code="JOURNAL_ENTRY"
            )
            journal_repo.save(reversing_journal)
            reversing_lines = [
                JournalEntryLine(
                    journal_entry_id=reversing_journal.id,
                    line_number=line.line_number,
                    account_id=line.account_id,
                    line_description=f"Reversal: {line.line_description or original_doc.document_number}",
                    debit_amount=line.credit_amount,
                    credit_amount=line.debit_amount,
                    contract_id=line.contract_id,
                    project_id=line.project_id,
                    project_job_id=line.project_job_id,
                    project_cost_code_id=line.project_cost_code_id,
                )
                for line in sorted(original_journal.lines, key=lambda row: row.line_number)
            ]
            uow.session.add_all(reversing_lines)

            reversal_doc.posted_journal_entry_id = reversing_journal.id
            original_doc.reversal_document_id = reversal_doc.id
            original_doc.reverse_reason_code_id = command.reason_code_id
            original_doc.reversed_at = reversed_at
            original_doc.reversed_by_user_id = actor_id
            original_doc.reversing_journal_entry_id = reversing_journal.id
            doc_repo.save(reversal_doc)
            doc_repo.save(original_doc)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_posting_integrity_error(exc) from exc

            from seeker_accounting.modules.audit.event_type_catalog import INVENTORY_DOCUMENT_REVERSED
            self._record_audit(company_id, INVENTORY_DOCUMENT_REVERSED, "InventoryDocument", original_doc.id, "Reversed inventory document")
            return InventoryReversalResultDTO(
                company_id=company_id,
                original_document_id=original_doc.id,
                reversal_document_id=reversal_doc.id,
                reversal_document_number=reversal_doc.document_number,
                reversing_journal_entry_id=reversing_journal.id,
                reversing_journal_entry_number=reversing_journal.entry_number or "",
                reversed_at=reversed_at,
                reversed_by_user_id=actor_id,
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_doc_type_action(self, doc_type_code: str) -> str:
        """Map a document type code to the legacy posting action."""
        if doc_type_code in _LEGACY_DOCUMENT_TYPES:
            return doc_type_code
        action = _DOC_TYPE_ACTION.get(doc_type_code)
        if action is None:
            raise ValidationError(
                f"Document type '{doc_type_code}' is not supported for posting."
            )
        return action

    def _require_company_exists(self, session: Session | None, company_id: int) -> None:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        repo = self._company_repository_factory(session)
        if repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

    def _inventory_sod_is_enforced(self, session: Session, company_id: int) -> bool:
        if self._company_preference_repository_factory is None:
            return False
        preference = self._company_preference_repository_factory(session).get_by_company_id(company_id)
        return bool(preference and preference.enforce_inventory_segregation_of_duties)

    def _require_permission(self, permission_code: str) -> None:
        if self._permission_service is not None:
            self._permission_service.require_permission(permission_code)

    def _enforce_budget_for_issue(
        self,
        doc: InventoryDocument,
        doc_line: InventoryDocumentLine,
        amount: Decimal,
    ) -> None:
        if self._budget_control_service is None:
            return
        project_id = doc_line.project_id or doc.project_id
        if project_id is None:
            return
        requested_amount = Decimal(amount).quantize(Decimal("0.01"))
        if requested_amount <= Decimal("0.00"):
            return
        self._budget_control_service.enforce_budget(
            project_id,
            requested_amount,
            project_job_id=doc_line.project_job_id,
            project_cost_code_id=doc_line.project_cost_code_id,
            context_label=f"Inventory issue line {doc_line.line_number}",
        )

    def _document_line_direction_and_quantity(
        self,
        doc: InventoryDocument,
        doc_line: InventoryDocumentLine,
    ) -> tuple[int, Decimal]:
        action = self._resolve_doc_type_action(doc.document_type_code)
        stock_quantity = doc_line.base_quantity if doc_line.base_quantity is not None else doc_line.quantity
        quantity_base = abs(stock_quantity)
        if action == "receipt":
            return 1, quantity_base
        if action == "issue":
            return -1, quantity_base
        return (1 if stock_quantity >= 0 else -1), quantity_base

    def _mark_serials_for_receipt(self, session: Session, doc_line, location_id: int | None) -> None:
        for link in doc_line.serial_links:
            serial = session.get(ItemSerial, link.serial_id)
            if serial is None:
                continue
            serial.status_code = "in_stock"
            serial.current_location_id = location_id
            serial.current_doc_line_id = doc_line.id

    def _mark_serials_for_issue(self, session: Session, doc_line, document_type_code: str) -> None:
        for link in doc_line.serial_links:
            serial = session.get(ItemSerial, link.serial_id)
            if serial is None:
                continue
            serial.status_code = "in_transit" if document_type_code in {"transfer_out", "transfer_in_transit"} else "issued"
            serial.current_doc_line_id = doc_line.id

    def _mark_serials_for_reversal(
        self,
        session: Session,
        doc_line: InventoryDocumentLine,
        reversal_direction: int,
        location_id: int | None,
    ) -> None:
        for link in doc_line.serial_links:
            serial = session.get(ItemSerial, link.serial_id)
            if serial is None:
                continue
            serial.current_doc_line_id = doc_line.id
            if reversal_direction > 0:
                serial.status_code = "in_stock"
                serial.current_location_id = location_id
            else:
                serial.status_code = "allocated"
                serial.current_location_id = None

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
