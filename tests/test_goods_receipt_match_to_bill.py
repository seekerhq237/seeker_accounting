from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from seeker_accounting.db import model_registry  # noqa: F401
from seeker_accounting.modules.inventory.models.purchase_receipt_link import (
    PurchaseBillLineReceiptLink,
)
from seeker_accounting.modules.inventory.services.goods_receipt_service import (
    GoodsReceiptService,
    GrnBillMatchLineCommand,
)
from seeker_accounting.platform.exceptions import ValidationError


class _FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.added_all: list[object] = []
        self._next_id = 1000

    def add(self, item: object) -> None:
        if getattr(item, "id", None) is None:
            try:
                setattr(item, "id", self._next_id)
                self._next_id += 1
            except AttributeError:
                pass
        self.added.append(item)

    def add_all(self, items: list[object]) -> None:
        self.added_all.extend(items)

    def flush(self) -> None:
        return None


class _FakeUnitOfWork:
    def __init__(self, session: _FakeSession) -> None:
        self.session = session
        self.committed = False

    def __enter__(self) -> _FakeUnitOfWork:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def commit(self) -> None:
        self.committed = True


class _JournalRepo:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    def add(self, journal_entry: object) -> object:
        self._session.add(journal_entry)
        return journal_entry


class _RoleMappingRepo:
    def __init__(self, roles: dict[str, int]) -> None:
        self._roles = roles

    def get_by_role_code(self, company_id: int, role_code: str) -> object | None:
        account_id = self._roles.get(role_code)
        if account_id is None:
            return None
        return SimpleNamespace(account_id=account_id)


class _BillRepo:
    def __init__(self, bill: object) -> None:
        self._bill = bill

    def get_detail(self, company_id: int, bill_id: int) -> object | None:
        if self._bill.company_id == company_id and self._bill.id == bill_id:
            return self._bill
        return None


class _DocumentRepo:
    def __init__(self, lines: list[object]) -> None:
        self._lines_by_id = {line.id: line for line in lines}

    def list_lines_by_ids(self, company_id: int, line_ids: list[int]) -> list[object]:
        return [self._lines_by_id[line_id] for line_id in line_ids if line_id in self._lines_by_id]

    def list_posted_goods_receipt_lines(self, company_id: int, purchase_order_id: int | None = None) -> list[object]:
        return list(self._lines_by_id.values())


class _ReceiptLinkRepo:
    def __init__(self, links: list[PurchaseBillLineReceiptLink] | None = None) -> None:
        self.links: list[PurchaseBillLineReceiptLink] = list(links or [])

    def list_bill_links_for_document(self, inventory_document_line_id: int) -> list[PurchaseBillLineReceiptLink]:
        return [
            link
            for link in self.links
            if link.inventory_document_line_id == inventory_document_line_id
        ]

    def list_bill_links_for_bill_line(self, company_id: int, bill_line_id: int) -> list[PurchaseBillLineReceiptLink]:
        return [
            link
            for link in self.links
            if link.company_id == company_id and link.purchase_bill_line_id == bill_line_id
        ]

    def add_bill_link(self, link: PurchaseBillLineReceiptLink) -> None:
        self.links.append(link)


class GoodsReceiptMatchToBillTests(unittest.TestCase):
    def _build_service(
        self,
        *,
        bill: object,
        doc_lines: list[object],
        links: list[PurchaseBillLineReceiptLink] | None = None,
        roles: dict[str, int] | None = None,
    ) -> tuple[GoodsReceiptService, _FakeSession, _FakeUnitOfWork, _ReceiptLinkRepo]:
        session = _FakeSession()
        uow = _FakeUnitOfWork(session)
        link_repo = _ReceiptLinkRepo(links)
        role_repo = _RoleMappingRepo(
            roles
            or {
                "grni_clearing": 200,
                "purchase_price_variance": 300,
            }
        )
        service = GoodsReceiptService(
            unit_of_work_factory=lambda: uow,
            stock_ledger_service=SimpleNamespace(),
            journal_entry_repository_factory=lambda session: _JournalRepo(session),
            account_role_mapping_repository_factory=lambda session: role_repo,
            inventory_document_repository_factory=lambda session: _DocumentRepo(doc_lines),
            purchase_bill_repository_factory=lambda session: _BillRepo(bill),
            purchase_order_repository_factory=lambda session: SimpleNamespace(),
            purchase_receipt_link_repository_factory=lambda session: link_repo,
        )
        return service, session, uow, link_repo

    def _posted_bill_and_grn_line(
        self,
        *,
        bill_subtotal: Decimal,
        receipt_unit_cost: Decimal = Decimal("10.00"),
        quantity: Decimal = Decimal("5.0000"),
    ) -> tuple[object, object]:
        bill_line = SimpleNamespace(
            id=10,
            line_number=1,
            description="Inventory purchase",
            item_id=55,
            quantity=quantity,
            base_quantity=quantity,
            unit_cost=bill_subtotal / quantity,
            line_subtotal_amount=bill_subtotal,
            expense_account_id=400,
            contract_id=None,
            project_id=None,
            project_job_id=None,
            project_cost_code_id=None,
        )
        bill = SimpleNamespace(
            id=5,
            company_id=1,
            bill_number="PB-001",
            bill_date=date(2026, 5, 6),
            status_code="posted",
            contract_id=None,
            project_id=None,
            lines=[bill_line],
        )
        grn = SimpleNamespace(
            id=20,
            company_id=1,
            document_number="GRN-001",
            document_date=date(2026, 5, 5),
            document_type_code="goods_receipt_purchase",
            status_code="posted",
        )
        doc_line = SimpleNamespace(
            id=30,
            inventory_document_id=grn.id,
            inventory_document=grn,
            item_id=55,
            quantity=quantity,
            base_quantity=quantity,
            unit_cost=receipt_unit_cost,
            item=SimpleNamespace(item_code="ITM-55", item_name="Inventory item"),
        )
        return bill, doc_line

    def test_get_match_options_returns_open_bill_and_receipt_quantities(self) -> None:
        bill, doc_line = self._posted_bill_and_grn_line(bill_subtotal=Decimal("60.00"))
        existing_link = PurchaseBillLineReceiptLink(
            company_id=1,
            purchase_bill_line_id=10,
            inventory_document_line_id=30,
            matched_qty=Decimal("2.0000"),
            matched_amount=Decimal("24.00"),
        )
        service, _session, _uow, _link_repo = self._build_service(
            bill=bill,
            doc_lines=[doc_line],
            links=[existing_link],
        )

        options = service.get_match_options(company_id=1, purchase_bill_id=bill.id)

        self.assertEqual(options.purchase_bill_id, bill.id)
        self.assertEqual(len(options.bill_lines), 1)
        self.assertEqual(options.bill_lines[0].matched_qty, Decimal("2.0000"))
        self.assertEqual(options.bill_lines[0].available_qty, Decimal("3.0000"))
        self.assertEqual(len(options.receipt_lines), 1)
        self.assertEqual(options.receipt_lines[0].matched_qty, Decimal("2.0000"))
        self.assertEqual(options.receipt_lines[0].available_qty, Decimal("3.0000"))
        self.assertEqual(options.receipt_lines[0].available_amount, Decimal("30.00"))

    def test_match_reclasses_posted_bill_cost_and_records_unfavorable_ppv(self) -> None:
        bill, doc_line = self._posted_bill_and_grn_line(bill_subtotal=Decimal("60.00"))
        service, session, uow, link_repo = self._build_service(bill=bill, doc_lines=[doc_line])

        result = service.match_to_bill(
            company_id=1,
            purchase_bill_id=bill.id,
            fiscal_period_id=99,
            lines=[
                GrnBillMatchLineCommand(
                    purchase_bill_line_id=10,
                    inventory_document_line_id=30,
                    matched_qty=Decimal("5.0000"),
                )
            ],
            actor_user_id=7,
        )

        self.assertTrue(uow.committed)
        self.assertEqual(result.grni_cleared_amount, Decimal("50.00"))
        self.assertEqual(result.bill_matched_amount, Decimal("60.00"))
        self.assertEqual(result.purchase_price_variance_amount, Decimal("10.00"))
        self.assertEqual(result.journal_entry_id, 1000)
        self.assertEqual(len(link_repo.links), 1)
        self.assertEqual(link_repo.links[0].matched_qty, Decimal("5.0000"))
        self.assertEqual(link_repo.links[0].matched_amount, Decimal("60.00"))

        lines = session.added_all
        self.assertEqual(sum(line.debit_amount for line in lines), Decimal("60.00"))
        self.assertEqual(sum(line.credit_amount for line in lines), Decimal("60.00"))
        by_account = {line.account_id: line for line in lines}
        self.assertEqual(by_account[200].debit_amount, Decimal("50.00"))
        self.assertEqual(by_account[400].credit_amount, Decimal("60.00"))
        self.assertEqual(by_account[300].debit_amount, Decimal("10.00"))

    def test_match_records_favorable_ppv_as_credit(self) -> None:
        bill, doc_line = self._posted_bill_and_grn_line(bill_subtotal=Decimal("45.00"))
        service, session, _uow, _link_repo = self._build_service(bill=bill, doc_lines=[doc_line])

        result = service.match_to_bill(
            company_id=1,
            purchase_bill_id=bill.id,
            fiscal_period_id=99,
            lines=[
                GrnBillMatchLineCommand(
                    purchase_bill_line_id=10,
                    inventory_document_line_id=30,
                    matched_qty=Decimal("5.0000"),
                )
            ],
        )

        self.assertEqual(result.purchase_price_variance_amount, Decimal("-5.00"))
        lines = session.added_all
        self.assertEqual(sum(line.debit_amount for line in lines), Decimal("50.00"))
        self.assertEqual(sum(line.credit_amount for line in lines), Decimal("50.00"))
        by_account = {line.account_id: line for line in lines}
        self.assertEqual(by_account[300].credit_amount, Decimal("5.00"))

    def test_match_blocks_overmatching_receipt_quantity(self) -> None:
        bill, doc_line = self._posted_bill_and_grn_line(bill_subtotal=Decimal("60.00"))
        existing_link = PurchaseBillLineReceiptLink(
            company_id=1,
            purchase_bill_line_id=999,
            inventory_document_line_id=30,
            matched_qty=Decimal("4.0000"),
            matched_amount=Decimal("40.00"),
        )
        service, session, uow, link_repo = self._build_service(
            bill=bill,
            doc_lines=[doc_line],
            links=[existing_link],
        )

        with self.assertRaises(ValidationError):
            service.match_to_bill(
                company_id=1,
                purchase_bill_id=bill.id,
                fiscal_period_id=99,
                lines=[
                    GrnBillMatchLineCommand(
                        purchase_bill_line_id=10,
                        inventory_document_line_id=30,
                        matched_qty=Decimal("2.0000"),
                    )
                ],
            )

        self.assertFalse(uow.committed)
        self.assertEqual(session.added_all, [])
        self.assertEqual(link_repo.links, [existing_link])


if __name__ == "__main__":
    unittest.main()