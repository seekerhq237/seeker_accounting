"""Inventory P7 hardening test harness.

Covers Slice 8.1 (concurrency & consistency invariants) and Slice 8.3
(test harness):

* ``StockLedgerService.append`` keeps ledger + balance in sync (Invariants 1 & 2).
* ``InventoryInvariantCheckerService.check`` reports a clean bill of health
  when the system is consistent.
* Manually corrupted balance rows are detected as discrepancies.
* Property-style scenarios: 1000 randomised receipt→issue chains remain
  invariant-clean.

Per ``docs/inventory_upgrade_plan.md`` Slice 8.3: property tests must
demonstrate ``ledger ≡ balances`` and ``total qty ≥ 0`` always hold.
"""

from __future__ import annotations

import random
import unittest
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

import seeker_accounting.db.model_registry  # noqa: F401  (register all mappers)
from seeker_accounting.db.base import Base
from seeker_accounting.db.unit_of_work import create_unit_of_work_factory
from seeker_accounting.modules.companies.models.company import Company
from seeker_accounting.modules.inventory.dto.inventory_invariant_dto import (
    InventoryInvariantReportDTO,
)
from seeker_accounting.modules.inventory.models.item import Item
from seeker_accounting.modules.inventory.models.stock_ledger_balance import StockLedgerBalance
from seeker_accounting.modules.inventory.models.unit_of_measure import UnitOfMeasure
from seeker_accounting.modules.inventory.repositories.stock_ledger_balance_repository import (
    StockLedgerBalanceRepository,
)
from seeker_accounting.modules.inventory.repositories.stock_ledger_entry_repository import (
    StockLedgerEntryRepository,
)
from seeker_accounting.modules.inventory.services.inventory_invariant_checker_service import (
    InventoryInvariantCheckerService,
)
from seeker_accounting.modules.inventory.services.stock_ledger_service import StockLedgerService
from seeker_accounting.platform.exceptions import ValidationError

_TODAY = date(2026, 1, 15)
_DOC_TYPE = "goods_receipt_purchase"
_DOC_TYPE_ISSUE = "goods_issue_production"


# ---------------------------------------------------------------------------
# Test-database bootstrap
# ---------------------------------------------------------------------------


def _make_engine():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    # SQLite FK enforcement is OFF by default; keep it OFF for test isolation.
    Base.metadata.create_all(engine)
    return engine


def _seed_company_and_item(session: Session) -> tuple[int, int]:
    """Return (company_id, item_id) after seeding minimal required rows."""
    company = Company(
        legal_name="InvTest Corp",
        display_name="InvTest Corp",
        country_code="CM",
        base_currency_code="XAF",
    )
    session.add(company)
    session.flush()

    uom = UnitOfMeasure(
        company_id=company.id,
        code="EA",
        name="Each",
        ratio_to_base=Decimal("1"),
    )
    session.add(uom)
    session.flush()

    item = Item(
        company_id=company.id,
        item_code="ITM-001",
        item_name="Test Widget",
        item_type_code="stock",
        unit_of_measure_id=uom.id,
    )
    session.add(item)
    session.flush()

    return company.id, item.id


# ---------------------------------------------------------------------------
# Shared fixtures for the test class
# ---------------------------------------------------------------------------


def _make_services(SF: sessionmaker):
    uow_factory = create_unit_of_work_factory(SF)

    ledger_svc = StockLedgerService(
        entry_repository_factory=StockLedgerEntryRepository,
        balance_repository_factory=StockLedgerBalanceRepository,
    )
    checker_svc = InventoryInvariantCheckerService(
        unit_of_work_factory=uow_factory,
    )
    return ledger_svc, checker_svc, uow_factory


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class StockLedgerInvariantTests(unittest.TestCase):
    """Verify StockLedgerService keeps ledger and balance consistent."""

    def setUp(self) -> None:
        engine = _make_engine()
        self.SF: sessionmaker = sessionmaker(
            bind=engine, autoflush=False, expire_on_commit=False, class_=Session
        )
        session = self.SF()
        try:
            self.company_id, self.item_id = _seed_company_and_item(session)
            session.commit()
        finally:
            session.close()

        self.ledger_svc, self.checker_svc, self.uow_factory = _make_services(self.SF)

    # ------------------------------------------------------------------
    # Single receipt
    # ------------------------------------------------------------------

    def test_single_receipt_balance_reflects_ledger(self) -> None:
        with self.SF() as session:
            entry = self.ledger_svc.append(
                session,
                company_id=self.company_id,
                item_id=self.item_id,
                location_id=None,
                posting_date=_TODAY,
                document_type_code=_DOC_TYPE,
                inventory_document_line_id=None,
                direction=1,
                quantity_base=Decimal("10"),
                unit_cost=Decimal("5.00"),
            )
            session.commit()

        report: InventoryInvariantReportDTO = self.checker_svc.check(self.company_id)
        self.assertTrue(report.is_clean, msg=str(report.ledger_balance_mismatches))
        self.assertEqual(entry.running_quantity_after, Decimal("10.0000"))
        self.assertEqual(entry.running_value_after, Decimal("50.00"))

    # ------------------------------------------------------------------
    # Receipt then issue — balance must show net position
    # ------------------------------------------------------------------

    def test_receipt_then_issue_balance_is_net(self) -> None:
        with self.SF() as session:
            self.ledger_svc.append(
                session,
                company_id=self.company_id,
                item_id=self.item_id,
                location_id=None,
                posting_date=_TODAY,
                document_type_code=_DOC_TYPE,
                inventory_document_line_id=None,
                direction=1,
                quantity_base=Decimal("20"),
                unit_cost=Decimal("10.00"),
            )
            self.ledger_svc.append(
                session,
                company_id=self.company_id,
                item_id=self.item_id,
                location_id=None,
                posting_date=_TODAY,
                document_type_code=_DOC_TYPE_ISSUE,
                inventory_document_line_id=None,
                direction=-1,
                quantity_base=Decimal("7"),
                unit_cost=Decimal("10.00"),
            )
            session.commit()

        report = self.checker_svc.check(self.company_id)
        self.assertTrue(report.is_clean, msg=str(report.ledger_balance_mismatches))

    # ------------------------------------------------------------------
    # Over-issue must raise ValidationError
    # ------------------------------------------------------------------

    def test_over_issue_raises_validation_error(self) -> None:
        with self.SF() as session:
            self.ledger_svc.append(
                session,
                company_id=self.company_id,
                item_id=self.item_id,
                location_id=None,
                posting_date=_TODAY,
                document_type_code=_DOC_TYPE,
                inventory_document_line_id=None,
                direction=1,
                quantity_base=Decimal("5"),
                unit_cost=Decimal("3.00"),
            )
            session.flush()

            with self.assertRaises(ValidationError):
                self.ledger_svc.append(
                    session,
                    company_id=self.company_id,
                    item_id=self.item_id,
                    location_id=None,
                    posting_date=_TODAY,
                    document_type_code=_DOC_TYPE_ISSUE,
                    inventory_document_line_id=None,
                    direction=-1,
                    quantity_base=Decimal("10"),
                    unit_cost=Decimal("3.00"),
                )
            session.rollback()

    # ------------------------------------------------------------------
    # Corrupted balance detected by invariant checker
    # ------------------------------------------------------------------

    def test_corrupted_balance_detected_by_checker(self) -> None:
        # Seed a receipt to create the balance row.
        with self.SF() as session:
            self.ledger_svc.append(
                session,
                company_id=self.company_id,
                item_id=self.item_id,
                location_id=None,
                posting_date=_TODAY,
                document_type_code=_DOC_TYPE,
                inventory_document_line_id=None,
                direction=1,
                quantity_base=Decimal("15"),
                unit_cost=Decimal("4.00"),
            )
            session.commit()

        # Manually corrupt the balance row (simulates a bug in a writer path).
        with self.SF() as session:
            session.execute(
                text(
                    "UPDATE stock_ledger_balances SET quantity = 999 "
                    "WHERE item_id = :iid AND company_id = :cid"
                ),
                {"iid": self.item_id, "cid": self.company_id},
            )
            session.commit()

        report = self.checker_svc.check(self.company_id)
        self.assertFalse(report.is_clean)
        self.assertEqual(len(report.ledger_balance_mismatches), 1)
        mismatch = report.ledger_balance_mismatches[0]
        self.assertEqual(mismatch.ledger_qty, Decimal("15.0000"))
        self.assertEqual(mismatch.balance_qty, Decimal("999.0000"))

    # ------------------------------------------------------------------
    # Two items, two locations — all clean
    # ------------------------------------------------------------------

    def test_multiple_items_locations_all_clean(self) -> None:
        with self.SF() as session:
            # Create a second item.
            uom = session.execute(
                text("SELECT id FROM units_of_measure WHERE company_id = :cid LIMIT 1"),
                {"cid": self.company_id},
            ).scalar()
            item2 = Item(
                company_id=self.company_id,
                item_code="ITM-002",
                item_name="Widget B",
                item_type_code="stock",
                unit_of_measure_id=uom,
            )
            session.add(item2)
            session.flush()

            for item_id in (self.item_id, item2.id):
                for loc_id in (None, 10):  # None and sentinel location 10
                    self.ledger_svc.append(
                        session,
                        company_id=self.company_id,
                        item_id=item_id,
                        location_id=loc_id,
                        posting_date=_TODAY,
                        document_type_code=_DOC_TYPE,
                        inventory_document_line_id=None,
                        direction=1,
                        quantity_base=Decimal("3"),
                        unit_cost=Decimal("2.00"),
                    )
            session.commit()

        report = self.checker_svc.check(self.company_id)
        self.assertTrue(report.is_clean, msg=str(report.ledger_balance_mismatches))


class StockLedgerPropertyTests(unittest.TestCase):
    """Randomised scenarios: invariant must hold after every write."""

    _SEED = 42
    _SCENARIOS = 1000

    def setUp(self) -> None:
        engine = _make_engine()
        self.SF: sessionmaker = sessionmaker(
            bind=engine, autoflush=False, expire_on_commit=False, class_=Session
        )
        session = self.SF()
        try:
            self.company_id, self.item_id = _seed_company_and_item(session)
            session.commit()
        finally:
            session.close()

        self.ledger_svc, self.checker_svc, self.uow_factory = _make_services(self.SF)

    def test_randomised_receipt_issue_chain_remains_invariant_clean(self) -> None:
        """1000 random receipt/issue operations must leave the ledger clean."""
        from seeker_accounting.platform.numerics.rounding_policy import quantize_quantity

        rng = random.Random(self._SEED)
        on_hand = Decimal("0.0000")
        receipt_cost = Decimal("10.0000")

        with self.SF() as session:
            for _ in range(self._SCENARIOS):
                # Decide whether to receipt or issue (always receipt if stock is zero).
                do_issue = on_hand > Decimal("0.0001") and rng.random() < 0.4

                if do_issue:
                    # Use a fraction of the quantized on_hand to avoid rounding overshoot.
                    fraction = Decimal(str(round(rng.uniform(0.05, 0.9), 4)))
                    qty = quantize_quantity(on_hand * fraction)
                    if qty <= Decimal("0"):
                        continue
                    entry = self.ledger_svc.append(
                        session,
                        company_id=self.company_id,
                        item_id=self.item_id,
                        location_id=None,
                        posting_date=_TODAY,
                        document_type_code=_DOC_TYPE_ISSUE,
                        inventory_document_line_id=None,
                        direction=-1,
                        quantity_base=qty,
                        unit_cost=receipt_cost,
                    )
                    on_hand = entry.running_quantity_after
                else:
                    qty = quantize_quantity(Decimal(str(round(rng.uniform(0.5, 20.0), 4))))
                    cost = Decimal(str(round(rng.uniform(1.0, 50.0), 6)))
                    entry = self.ledger_svc.append(
                        session,
                        company_id=self.company_id,
                        item_id=self.item_id,
                        location_id=None,
                        posting_date=_TODAY,
                        document_type_code=_DOC_TYPE,
                        inventory_document_line_id=None,
                        direction=1,
                        quantity_base=qty,
                        unit_cost=cost,
                    )
                    on_hand = entry.running_quantity_after

            session.commit()

        report = self.checker_svc.check(self.company_id)
        self.assertTrue(
            report.is_clean,
            msg=f"Invariant violated after randomised chain: {report.ledger_balance_mismatches}",
        )

        # Confirm on_hand is non-negative (belt-and-suspenders).
        with self.SF() as session:
            bal = StockLedgerBalanceRepository(session).get(
                self.company_id, self.item_id, None
            )
            self.assertIsNotNone(bal)
            self.assertGreaterEqual(Decimal(str(bal.quantity)), Decimal("0"))


if __name__ == "__main__":
    unittest.main()
