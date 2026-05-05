"""COGS Sync Service — P2 / Slice 3.2.

Called from within the SalesInvoicePostingService (or credit note variant)
INSIDE the existing UoW transaction so COGS and revenue post atomically.

For each invoice line that links to a stockable item, this service:
  1. Looks up the current average cost from the stock ledger balance.
  2. Calls StockLedgerService.append() to issue base_quantity units out.
  3. Adds COGS journal lines (Dr COGS Cr Inventory) to the in-progress JE.
  4. Stamps unit_cost_at_issue and cogs_amount on the invoice line.

If an item or its location has no stock balance yet (pre-receipt), we skip
COGS silently and leave unit_cost_at_issue = 0 — a warning-level gap the
reporting layer can surface.

Design constraint: this service does NOT own a UoW. It is handed the session
by the caller and must flush (not commit) when it needs IDs.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from seeker_accounting.modules.accounting.journals.models.journal_entry_line import (
    JournalEntryLine,
)
from seeker_accounting.modules.inventory.repositories.item_repository import ItemRepository
from seeker_accounting.modules.inventory.repositories.stock_ledger_balance_repository import (
    StockLedgerBalanceRepository,
)
from seeker_accounting.modules.inventory.services.stock_ledger_service import (
    StockLedgerService,
)
from seeker_accounting.platform.numerics.rounding_policy import (
    quantize_amount,
    quantize_internal_cost,
    quantize_quantity,
)

if TYPE_CHECKING:
    from seeker_accounting.modules.sales.models.sales_invoice import SalesInvoice
    from seeker_accounting.modules.sales.models.sales_invoice_line import SalesInvoiceLine

_ZERO = Decimal("0")
_ZERO_COST = Decimal("0.000000")
_ZERO_AMT = Decimal("0.00")


class CogsSyncService:
    """Append stock issues and build COGS journal lines for a posted invoice.

    This is a **session-scoped collaborator**, not a standalone service with
    its own UoW.  Inject it into SalesInvoicePostingService as an optional
    dependency; if absent (not configured), COGS is skipped for backward
    compat with companies that have no inventory items on invoices.
    """

    def __init__(
        self,
        stock_ledger_service: StockLedgerService,
    ) -> None:
        self._stock_ledger_service = stock_ledger_service

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_cogs_lines_for_invoice(
        self,
        session: Session,
        *,
        company_id: int,
        invoice: "SalesInvoice",
        journal_entry_id: int,
        next_line_number: int,
        posting_date: date,
    ) -> list[JournalEntryLine]:
        """Issue stock and return COGS journal lines to add to the JE.

        Modifies invoice lines in-place (unit_cost_at_issue, cogs_amount).
        Returns an (possibly empty) list of JournalEntryLines to append.
        """
        item_repo = ItemRepository(session)
        balance_repo = StockLedgerBalanceRepository(session)

        cogs_lines: list[JournalEntryLine] = []
        line_num = next_line_number

        for inv_line in invoice.lines:
            if not inv_line.item_id:
                continue

            item = item_repo.get(inv_line.item_id)
            if item is None or not item.is_stockable:
                continue
            if not item.cogs_account_id or not item.inventory_account_id:
                # Misconfigured — skip silently; caller can warn
                continue

            base_qty = _effective_base_qty(inv_line)
            if base_qty <= _ZERO:
                continue

            # Resolve current average cost from balance
            balance = balance_repo.get(company_id, item.id, location_id=None)
            if balance is None or balance.avg_cost <= _ZERO_COST:
                # No stock yet — issue at zero cost (will show as gap in reports)
                unit_cost = _ZERO_COST
            else:
                unit_cost = balance.avg_cost

            cogs_value = quantize_amount(base_qty * unit_cost)

            # Append stock ledger issue entry
            self._stock_ledger_service.append(
                session,
                company_id=company_id,
                item_id=item.id,
                location_id=None,
                posting_date=posting_date,
                document_type_code="sales_invoice_issue",
                inventory_document_line_id=None,
                direction=-1,
                quantity_base=base_qty,
                unit_cost=unit_cost,
            )

            # Stamp cost on the invoice line
            inv_line.unit_cost_at_issue = quantize_internal_cost(unit_cost)
            inv_line.cogs_amount = cogs_value

            # Dr COGS
            cogs_lines.append(
                JournalEntryLine(
                    journal_entry_id=journal_entry_id,
                    line_number=line_num,
                    account_id=item.cogs_account_id,
                    line_description=f"COGS – {item.item_name}",
                    debit_amount=cogs_value,
                    credit_amount=_ZERO_AMT,
                )
            )
            line_num += 1

            # Cr Inventory
            cogs_lines.append(
                JournalEntryLine(
                    journal_entry_id=journal_entry_id,
                    line_number=line_num,
                    account_id=item.inventory_account_id,
                    line_description=f"Inventory relief – {item.item_name}",
                    debit_amount=_ZERO_AMT,
                    credit_amount=cogs_value,
                )
            )
            line_num += 1

        return cogs_lines

    def build_cogs_reversal_for_credit_note(
        self,
        session: Session,
        *,
        company_id: int,
        credit_note_lines: list,
        journal_entry_id: int,
        next_line_number: int,
        posting_date: date,
    ) -> list[JournalEntryLine]:
        """Re-receive stock and return reversal COGS lines for a credit note.

        Uses unit_cost_at_issue from the originating invoice line if available,
        otherwise falls back to current average cost.
        """
        item_repo = ItemRepository(session)
        balance_repo = StockLedgerBalanceRepository(session)

        reversal_lines: list[JournalEntryLine] = []
        line_num = next_line_number

        for cn_line in credit_note_lines:
            if not cn_line.item_id:
                continue

            item = item_repo.get(cn_line.item_id)
            if item is None or not item.is_stockable:
                continue
            if not item.cogs_account_id or not item.inventory_account_id:
                continue

            base_qty = _effective_base_qty(cn_line)
            if base_qty <= _ZERO:
                continue

            # Use original cost when stamped; fall back to current avg
            unit_cost = getattr(cn_line, "unit_cost_at_issue", None) or _ZERO_COST
            if unit_cost <= _ZERO_COST:
                balance = balance_repo.get(company_id, item.id, location_id=None)
                unit_cost = balance.avg_cost if (balance and balance.avg_cost > _ZERO_COST) else _ZERO_COST

            cogs_value = quantize_amount(base_qty * unit_cost)

            # Re-receive stock (direction +1)
            self._stock_ledger_service.append(
                session,
                company_id=company_id,
                item_id=item.id,
                location_id=None,
                posting_date=posting_date,
                document_type_code="sales_credit_note_return",
                inventory_document_line_id=None,
                direction=1,
                quantity_base=base_qty,
                unit_cost=unit_cost,
            )

            cn_line.unit_cost_at_issue = quantize_internal_cost(unit_cost)
            cn_line.cogs_amount = cogs_value

            # Cr COGS (reversal)
            reversal_lines.append(
                JournalEntryLine(
                    journal_entry_id=journal_entry_id,
                    line_number=line_num,
                    account_id=item.cogs_account_id,
                    line_description=f"COGS reversal – {item.item_name}",
                    debit_amount=_ZERO_AMT,
                    credit_amount=cogs_value,
                )
            )
            line_num += 1

            # Dr Inventory (reversal)
            reversal_lines.append(
                JournalEntryLine(
                    journal_entry_id=journal_entry_id,
                    line_number=line_num,
                    account_id=item.inventory_account_id,
                    line_description=f"Inventory return – {item.item_name}",
                    debit_amount=cogs_value,
                    credit_amount=_ZERO_AMT,
                )
            )
            line_num += 1

        return reversal_lines


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _effective_base_qty(line) -> Decimal:
    """Return base_quantity if set, otherwise fall back to quantity."""
    base = getattr(line, "base_quantity", None)
    if base is not None and base > _ZERO:
        return quantize_quantity(base)
    qty = getattr(line, "quantity", _ZERO)
    return quantize_quantity(qty) if qty else _ZERO
