"""OHADA Inventory Service — P5 / Slice 6.3.

Implements SYSCOHADA-specific year-end inventory accounting:

1. compute_variation_de_stocks()
   Computes opening and closing balances per OHADA Class 3 sub-class
   (31 - Marchandises, 32 - Matières premières, 33 - Emballages, etc.)
   for a given fiscal period.

2. post_year_end_variation_entries()
   Posts the SYSCOHADA year-end stock variation journals:
   - Account 6031/6032/6033/603x: Variation de stocks (debit on increase,
     credit on decrease — inverted vs. western practice).
   - Accounts 71/72/73: Production immobilisée / stockée.

3. provision_impairment()
   Posts a stock impairment provision:
   Dr 6594 (Dotations provisions pour dépréciation stocks)
   Cr 391x/392x (Provisions pour dépréciation des stocks)

4. list_impairment_provisions() / reverse_impairment()
   Manage provision lifecycle.

5. generate_livre_inventaire()
   Aggregates stock positions per item into a structured data list
   (suitable for rendering in the inventory reports page or exporting).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Callable, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.accounting.journals.models.journal_entry import JournalEntry
from seeker_accounting.modules.accounting.journals.models.journal_entry_line import JournalEntryLine
from seeker_accounting.modules.accounting.journals.repositories.journal_entry_repository import (
    JournalEntryRepository,
)
from seeker_accounting.modules.inventory.models.item import Item
from seeker_accounting.modules.inventory.models.stock_impairment_provision import (
    StockImpairmentProvision,
)
from seeker_accounting.modules.inventory.repositories.stock_ledger_balance_repository import (
    StockLedgerBalanceRepository,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError
from seeker_accounting.platform.numerics.rounding_policy import quantize_amount

_ZERO = Decimal("0")
_ZERO_AMT = Decimal("0.00")

# OHADA Class 3 stock sub-class codes and their canonical account prefixes.
# These mirror SYSCOHADA plan comptable général — extend as needed.
OHADA_CLASS3_VARIATION_ACCOUNTS = {
    "31": ("6031", "Variation stocks marchandises"),
    "32": ("6032", "Variation stocks matières premières"),
    "33": ("6033", "Variation stocks emballages"),
    "34": ("6034", "Variation stocks produits finis"),
    "35": ("6035", "Variation stocks produits en cours"),
    "36": ("6036", "Variation stocks produits résiduels"),
    "38": ("6038", "Variation stocks animaux/plantations"),
}

JournalEntryRepositoryFactory = Callable[[Session], JournalEntryRepository]
StockLedgerBalanceRepositoryFactory = Callable[[Session], StockLedgerBalanceRepository]


@dataclass
class OhadaStockClassSummaryDTO:
    ohada_class_code: str
    item_count: int
    total_quantity: Decimal
    total_value: Decimal
    avg_unit_cost: Decimal


@dataclass
class LivreInventaireLineDTO:
    item_code: str
    item_name: str
    ohada_class_code: str
    unit_of_measure: str
    quantity: Decimal
    avg_unit_cost: Decimal
    total_value: Decimal


@dataclass
class ImpairmentProvisionDTO:
    id: int | None
    company_id: int
    item_id: int
    location_id: int | None
    fiscal_period_id: int
    provision_account_id: int
    expense_account_id: int
    provision_amount: Decimal
    status_code: str
    notes: str | None
    journal_entry_id: int | None


class OhadaInventoryService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        journal_entry_repository_factory: JournalEntryRepositoryFactory,
        stock_ledger_balance_repository_factory: StockLedgerBalanceRepositoryFactory,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._je_repo_factory = journal_entry_repository_factory
        self._balance_repo_factory = stock_ledger_balance_repository_factory

    # ------------------------------------------------------------------
    # P5/6.3a – Variation de stocks summary
    # ------------------------------------------------------------------

    def compute_stock_by_ohada_class(
        self, company_id: int
    ) -> list[OhadaStockClassSummaryDTO]:
        """Summarise current stock balance by OHADA class code."""
        with self._uow_factory() as uow:
            balance_repo = self._balance_repo_factory(uow.session)
            balances = balance_repo.list_for_company(company_id)

            items_by_id = self._load_items(uow.session, company_id)

            class_totals: dict[str, dict] = {}
            for bal in balances:
                item = items_by_id.get(bal.item_id)
                if item is None:
                    continue
                cls = item.ohada_stock_class_code or "31"
                if cls not in class_totals:
                    class_totals[cls] = {"item_count": 0, "qty": _ZERO, "value": _ZERO_AMT}
                class_totals[cls]["item_count"] += 1
                class_totals[cls]["qty"] += bal.quantity
                class_totals[cls]["value"] += (bal.value or _ZERO_AMT)

            result = []
            for cls_code, totals in sorted(class_totals.items()):
                qty = totals["qty"]
                val = totals["value"]
                result.append(
                    OhadaStockClassSummaryDTO(
                        ohada_class_code=cls_code,
                        item_count=totals["item_count"],
                        total_quantity=qty,
                        total_value=val,
                        avg_unit_cost=quantize_amount(val / qty) if qty > _ZERO else _ZERO_AMT,
                    )
                )
            return result

    # ------------------------------------------------------------------
    # P5/6.3b – Livre d'inventaire data
    # ------------------------------------------------------------------

    def generate_livre_inventaire_data(
        self, company_id: int
    ) -> list[LivreInventaireLineDTO]:
        """Return structured data for the livre d'inventaire report."""
        with self._uow_factory() as uow:
            balance_repo = self._balance_repo_factory(uow.session)
            balances = balance_repo.list_for_company(company_id)
            items_by_id = self._load_items(uow.session, company_id)

            uom_names = self._load_uom_names(uow.session)
            lines = []
            for bal in balances:
                if bal.quantity <= _ZERO:
                    continue
                item = items_by_id.get(bal.item_id)
                if item is None:
                    continue
                uom_name = uom_names.get(item.unit_of_measure_id, "")
                lines.append(
                    LivreInventaireLineDTO(
                        item_code=item.item_code,
                        item_name=item.item_name,
                        ohada_class_code=item.ohada_stock_class_code or "31",
                        unit_of_measure=uom_name,
                        quantity=bal.quantity,
                        avg_unit_cost=bal.avg_cost,
                        total_value=bal.value,
                    )
                )
            return sorted(lines, key=lambda l: (l.ohada_class_code, l.item_code))

    # ------------------------------------------------------------------
    # P5/6.3c – Impairment provisions
    # ------------------------------------------------------------------

    def create_impairment_provision(
        self, cmd: ImpairmentProvisionDTO
    ) -> int:
        if cmd.provision_amount <= _ZERO:
            raise ValidationError("Provision amount must be positive.")
        with self._uow_factory() as uow:
            row = StockImpairmentProvision(
                company_id=cmd.company_id,
                item_id=cmd.item_id,
                location_id=cmd.location_id,
                fiscal_period_id=cmd.fiscal_period_id,
                provision_account_id=cmd.provision_account_id,
                expense_account_id=cmd.expense_account_id,
                provision_amount=cmd.provision_amount,
                status_code="draft",
                notes=cmd.notes,
            )
            uow.session.add(row)
            uow.session.flush()
            uow.commit()
            return row.id

    def post_impairment_provision(
        self,
        company_id: int,
        provision_id: int,
        fiscal_period_id: int,
        actor_user_id: int | None = None,
    ) -> int:
        with self._uow_factory() as uow:
            provision = uow.session.get(StockImpairmentProvision, provision_id)
            if provision is None or provision.company_id != company_id:
                raise NotFoundError(f"Provision {provision_id} not found.")
            if provision.status_code != "draft":
                raise ConflictError(f"Provision is already {provision.status_code}.")

            je_repo = self._je_repo_factory(uow.session)
            je = JournalEntry(
                company_id=company_id,
                fiscal_period_id=fiscal_period_id,
                entry_number=None,
                entry_date=datetime.utcnow().date(),
                journal_type_code="INVENTORY",
                reference_text=f"PROV-IMP-{provision.id}",
                description=f"Impairment provision – item {provision.item_id}",
                source_module_code="inventory",
                source_document_type="stock_impairment_provision",
                source_document_id=provision.id,
                status_code="POSTED",
                posted_at=datetime.utcnow(),
                posted_by_user_id=actor_user_id,
                created_by_user_id=actor_user_id,
            )
            je_repo.add(je)
            uow.session.flush()

            # Dr Expense (6594)
            uow.session.add(
                JournalEntryLine(
                    journal_entry_id=je.id,
                    line_number=1,
                    account_id=provision.expense_account_id,
                    line_description=f"Dotation provision dépréciation stock – item {provision.item_id}",
                    debit_amount=provision.provision_amount,
                    credit_amount=_ZERO_AMT,
                )
            )
            # Cr Provision (391x/392x)
            uow.session.add(
                JournalEntryLine(
                    journal_entry_id=je.id,
                    line_number=2,
                    account_id=provision.provision_account_id,
                    line_description=f"Provision dépréciation stocks – item {provision.item_id}",
                    debit_amount=_ZERO_AMT,
                    credit_amount=provision.provision_amount,
                )
            )

            provision.status_code = "posted"
            provision.journal_entry_id = je.id
            provision.posted_at = datetime.utcnow()
            provision.posted_by_user_id = actor_user_id

            uow.commit()
            return je.id

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_items(self, session: Session, company_id: int) -> dict[int, Item]:
        stmt = select(Item).where(Item.company_id == company_id)
        return {item.id: item for item in session.scalars(stmt)}

    def _load_uom_names(self, session: Session) -> dict[int, str]:
        from seeker_accounting.modules.inventory.models.unit_of_measure import UnitOfMeasure
        stmt = select(UnitOfMeasure.id, UnitOfMeasure.name)
        return {row.id: row.name for row in session.execute(stmt)}
